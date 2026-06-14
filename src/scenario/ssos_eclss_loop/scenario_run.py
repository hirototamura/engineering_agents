"""SsosEclssLoopScenario — EclssBackend poll loop with agent operational commands."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from core.event_log import EventLog
from core.scenario import Scenario
from environment.ssos.eclss_backend import EclssBackend
from environment.ssos.eclss_types import EclssTelemetrySnapshot
from integrations.one_piece import export_run_provenance
from scenario.agents.eclss_loop_types import EclssLoopObservation
from scenario.agents.ssos_eclss_loop_team import SsosEclssLoopTeam
from scenario.runner import (
    _deep_merge,
    agents_config_path,
    load_agents_config,
    scenario_config_path,
)
from scenario.ssos_eclss_loop.health import compute_eclss_storage_health
from scenario.ssos_eclss_loop.loop_mock_backend import LoopMockEclssBackend

logger = logging.getLogger(__name__)

BACKEND_ENV_VAR = "SSOS_ECLSS_BACKEND"


def _omit_nulls(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _telemetry_summary_fields(
    last_snap: Optional[EclssTelemetrySnapshot],
    peak_co2: Optional[float],
    min_o2: Optional[float],
) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    if peak_co2 is not None:
        fields["peak_co2_storage_kg"] = round(peak_co2, 2)
    if last_snap is not None:
        if last_snap.co2_storage_kg is not None:
            fields["final_co2_storage_kg"] = last_snap.co2_storage_kg
        if last_snap.o2_storage_kg is not None:
            fields["final_o2_storage_kg"] = last_snap.o2_storage_kg
        if last_snap.product_water_reserve_l is not None:
            fields["final_product_water_reserve_l"] = last_snap.product_water_reserve_l
        if last_snap.raw_topics:
            fields["telemetry_topics_read"] = sorted(last_snap.raw_topics.keys())
    if min_o2 is not None:
        fields["min_o2_storage_kg"] = round(min_o2, 2)
    return fields


def resolve_backend_kind(
    config: Dict[str, Any],
    overrides: Optional[Dict[str, Any]] = None,
) -> str:
    if overrides:
        backend_override = overrides.get("backend") or {}
        kind = backend_override.get("kind")
        if kind:
            return str(kind)
    env_kind = os.environ.get(BACKEND_ENV_VAR)
    if env_kind:
        return env_kind
    return str(config.get("backend", {}).get("kind", "mock"))


def build_eclss_backend(config: Dict[str, Any], kind: Optional[str] = None) -> EclssBackend:
    backend_kind = kind or resolve_backend_kind(config)
    if backend_kind == "mock":
        return LoopMockEclssBackend(config)
    if backend_kind == "ros2":
        from environment.ssos.ros2_eclss_bridge import Ros2EclssBridge

        ros2_cfg = config.get("backend", {}).get("ros2", {}) or {}
        return Ros2EclssBridge(
            action_timeout_s=float(ros2_cfg.get("action_timeout_s", 120.0)),
            topic_timeout_s=float(ros2_cfg.get("topic_timeout_s", 15.0)),
        )
    raise ValueError(f"Unknown ECLSS backend kind: {backend_kind!r} (expected mock or ros2)")


class SsosEclssLoopScenario(Scenario):
    @property
    def name(self) -> str:
        return "ssos_eclss_loop"

    def load_config(self, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with scenario_config_path(self.name).open(encoding="utf-8") as f:
            config = yaml.safe_load(f)
        if overrides:
            config = _deep_merge(config, overrides)
        return config

    def build_simulator(self, config: Dict[str, Any]):
        raise NotImplementedError("ssos_eclss_loop uses EclssBackend, not SimulatorProtocol")

    def build_team(self, config: Dict[str, Any]) -> Optional[SsosEclssLoopTeam]:
        agents_config = load_agents_config(self.name, config)
        if not agents_config:
            return None
        mode = agents_config.get("mode")
        if mode not in {"labeled_rule_base", "llm"}:
            return None
        return SsosEclssLoopTeam(agents_config)

    def run(
        self,
        output_dir: Optional[Path] = None,
        overrides: Optional[Dict[str, Any]] = None,
        recreate_output: bool = True,
    ) -> Path:
        config = self.load_config(overrides)
        agents_config = load_agents_config(self.name, config)
        sim_cfg = config.get("simulation", {})
        steps = int(sim_cfg.get("steps", 8))
        output_cfg = config.get("output", {})
        thresholds = config.get("thresholds", {}) or {}
        backend_kind = resolve_backend_kind(config, overrides)

        results_base = Path(__file__).resolve().parents[2] / "experiments" / "results"
        if output_dir is None:
            run_id = output_cfg.get("run_id", self.name)
            if agents_config and agents_config.get("mode") == "labeled_rule_base":
                run_id = output_cfg.get(
                    "run_id_labeled_rule_base",
                    f"{self.name}_labeled_rule_base",
                )
            elif agents_config and agents_config.get("mode") == "llm":
                run_id = output_cfg.get("run_id_llm", f"{self.name}_llm")
            if recreate_output:
                run_dir = EventLog.prepare_run_dir(results_base, run_id=run_id)
            else:
                run_dir = results_base / run_id
                run_dir.mkdir(parents=True, exist_ok=True)
        else:
            run_dir = Path(output_dir)
            if recreate_output and run_dir.exists():
                shutil.rmtree(run_dir)
            run_dir.mkdir(parents=True, exist_ok=True)

        backend = build_eclss_backend(config, kind=backend_kind)
        team = self.build_team(config)
        log = EventLog(run_dir)

        message_count = 0
        operational_command_count = 0
        ars_invoked_step: Optional[int] = None
        ogs_invoked_step: Optional[int] = None
        co2_requested_step: Optional[int] = None
        last_snap: Optional[EclssTelemetrySnapshot] = None
        last_health: Optional[Dict[str, Any]] = None
        peak_co2: Optional[float] = None
        min_o2: Optional[float] = None

        for step in range(steps):
            if isinstance(backend, LoopMockEclssBackend) and step > 0:
                backend.advance_step()

            snap = backend.poll_telemetry()
            last_snap = snap
            if snap.co2_storage_kg is not None:
                peak_co2 = (
                    snap.co2_storage_kg
                    if peak_co2 is None
                    else max(peak_co2, snap.co2_storage_kg)
                )
            if snap.o2_storage_kg is not None:
                min_o2 = (
                    snap.o2_storage_kg
                    if min_o2 is None
                    else min(min_o2, snap.o2_storage_kg)
                )

            health = compute_eclss_storage_health(step, snap, thresholds)
            last_health = health
            log.append("telemetry", {"step": step, **snap.to_dict()})
            log.append("health_metrics", health)

            if team is not None:
                obs = EclssLoopObservation(step=step, telemetry=snap, health=health)
                outcome = team.run_step(obs)
                events = team.apply_outcome(backend, outcome)
                operational_command_count += len(outcome.commands)
                for msg in outcome.messages:
                    log.append("messages", msg.to_dict())
                    message_count += 1
                for event in events:
                    log.append("events", {"step": step, **event})
                    cmd = (event.get("command") or {})
                    cmd_kind = cmd.get("kind")
                    if cmd_kind == "air_revitalisation" and ars_invoked_step is None:
                        ars_invoked_step = step
                    elif cmd_kind == "oxygen_generation" and ogs_invoked_step is None:
                        ogs_invoked_step = step
                    elif cmd_kind == "request_co2" and co2_requested_step is None:
                        co2_requested_step = step

        summary: Dict[str, Any] = {
            "scenario": self.name,
            "backend": backend_kind,
            "agents_mode": (agents_config or {}).get("mode", "none"),
            "steps": steps,
            **_telemetry_summary_fields(last_snap, peak_co2, min_o2),
            "final_health": last_health,
            "message_count": message_count,
            "operational_command_count": operational_command_count,
        }
        summary.update(
            _omit_nulls(
                {
                    "ars_invoked_step": ars_invoked_step,
                    "ogs_invoked_step": ogs_invoked_step,
                    "co2_requested_step": co2_requested_step,
                }
            )
        )

        if isinstance(team, SsosEclssLoopTeam):
            summary["team_count"] = team.team_cfg.count
            summary["agent_ids"] = list(team.team_cfg.agent_ids)

        log.write_summary(summary)

        provenance_path = run_dir / "provenance.jsonl"
        provenance_count = 0
        try:
            provenance_path = export_run_provenance(run_dir)
            with provenance_path.open(encoding="utf-8") as f:
                provenance_count = sum(1 for line in f if line.strip())
        except Exception as exc:
            logger.warning("One Piece provenance export failed: %s", exc)
        summary["provenance_path"] = str(provenance_path)
        summary["provenance_record_count"] = provenance_count
        log.write_summary(summary)
        return run_dir


SCENARIO_REGISTRY: Dict[str, Scenario] = {
    "ssos_eclss_loop": SsosEclssLoopScenario(),
}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run ssos_eclss_loop scenario")
    parser.add_argument(
        "--backend",
        choices=("mock", "ros2"),
        help=f"EclssBackend kind (default: scenario.yaml or {BACKEND_ENV_VAR} env)",
    )
    parser.add_argument("--output-dir", type=Path, help="Run output directory")
    parser.add_argument(
        "--agents-mode",
        choices=("none", "labeled_rule_base", "llm"),
        help="Override agents.mode from scenario.yaml",
    )
    parser.add_argument("--steps", type=int, help="Override simulation.steps")
    args = parser.parse_args(argv)

    overrides: Dict[str, Any] = {}
    if args.backend:
        overrides["backend"] = {"kind": args.backend}
    if args.agents_mode:
        overrides["agents"] = {"mode": args.agents_mode}
    if args.steps is not None:
        overrides["simulation"] = {"steps": args.steps}

    run_dir = SsosEclssLoopScenario().run(output_dir=args.output_dir, overrides=overrides or None)
    print(json.dumps(json.loads((run_dir / "summary.json").read_text(encoding="utf-8")), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
