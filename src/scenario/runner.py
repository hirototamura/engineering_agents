"""Scenario runner — loads YAML and drives Mock ECLSS with EventLog output."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.event_log import EventLog
from environment.eclss_ops.design_state import DesignStateManager
from environment.eclss_ops.telemetry import compute_health_metrics
from environment.protocol import AnomalySpec, HealthStatus, SimulatorProtocol
from environment.ssos.mock_eclss import MockEclssSimulator
from environment.ssos.station_simulator import StationSimulator
from environment.ssos.eps_stack import EpsStack
from environment.ssos.mock_sarj import MockSarj
from environment.ssos.topics import EVENT_RECOVERY
from integrations.one_piece import export_run_provenance
from scenario.agents.scrubber_degradation_team import ScrubberDegradationTeam
from scenario.agents.types import AgentObservation

SCENARIO_ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def list_scenarios() -> List[str]:
    names = []
    for path in SCENARIO_ROOT.iterdir():
        if path.is_dir() and (path / "scenario.yaml").exists():
            names.append(path.name)
    return sorted(names)


def scenario_config_path(name: str) -> Path:
    path = SCENARIO_ROOT / name / "scenario.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Scenario not found: {name} ({path})")
    return path


def agents_config_path(name: str) -> Path:
    return SCENARIO_ROOT / name / "agents.yaml"


def load_scenario_config(name: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with scenario_config_path(name).open(encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if overrides:
        config = _deep_merge(config, overrides)
    return config


def load_agents_config(name: str, scenario_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    agents_section = scenario_config.get("agents") or {}
    mode = agents_section.get("mode", "none")
    if mode == "none":
        return None

    agents_path = agents_config_path(name)
    if agents_path.exists():
        with agents_path.open(encoding="utf-8") as f:
            agents_yaml = yaml.safe_load(f) or {}
    else:
        agents_yaml = {}

    merged = _deep_merge(agents_yaml, {k: v for k, v in agents_section.items() if k != "config_file"})
    merged["mode"] = mode
    return merged


def _deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def build_eclss(config: Dict[str, Any]) -> MockEclssSimulator:
    sim_cfg = config.get("simulation", {})
    design_params = config.get("design_parameters")
    design = DesignStateManager(parameters=design_params) if design_params else DesignStateManager()

    eclss = MockEclssSimulator(
        initial_co2_ppm=float(sim_cfg.get("initial_co2_ppm", 800.0)),
        initial_power_margin_w=float(sim_cfg.get("initial_power_margin_w", 150.0)),
        design=design,
    )

    for anomaly in config.get("anomalies", []):
        eclss.inject_anomaly(
            AnomalySpec(
                name=anomaly["name"],
                start_step=int(anomaly["start_step"]),
                scrubber_efficiency_decay_per_step=float(
                    anomaly.get("scrubber_efficiency_decay_per_step", 0.01)
                ),
                power_margin_decay_per_step=float(anomaly.get("power_margin_decay_per_step", 5.0)),
                co2_production_multiplier=float(anomaly.get("co2_production_multiplier", 1.0)),
            )
        )
    return eclss


def build_eps_stack(config: Dict[str, Any]) -> EpsStack:
    eps_cfg = config.get("eps", {}) or {}
    sarj_cfg = eps_cfg.get("sarj", {}) or {}
    eclipse_window = sarj_cfg.get("eclipse_window")
    sarj = MockSarj(
        beta_angle_deg=float(sarj_cfg.get("beta_angle_deg", 45.0)),
        eclipse_window=tuple(eclipse_window) if eclipse_window else None,
    )
    return EpsStack(sarj=sarj)


def build_station_simulator(config: Dict[str, Any]) -> StationSimulator:
    return StationSimulator(eclss=build_eclss(config), eps=build_eps_stack(config))


def build_simulator(config: Dict[str, Any]) -> StationSimulator:
    """Build coupled ECLSS + EPS station (default entry point for scenarios)."""
    return build_station_simulator(config)


def build_agent_team(scenario_name: str, agents_config: Optional[Dict[str, Any]]):
    if not agents_config:
        return None
    mode = agents_config.get("mode")
    if mode not in {"labeled", "labeled_llm_guarded"}:
        return None
    if scenario_name == "scrubber_degradation":
        return ScrubberDegradationTeam(agents_config)
    raise ValueError(f"No labeled agent team for scenario: {scenario_name}")


def _log_sim_events(log: EventLog, sim: SimulatorProtocol, step: int, logged_event_ids: set) -> None:
    for idx, event in enumerate(sim.get_events()):
        if "step" not in event:
            key = ("static", idx, event.get("kind"), json.dumps(event, sort_keys=True, default=str))
            if key in logged_event_ids:
                continue
            logged_event_ids.add(key)
            log.append("events", {"step": 0, **event})
            continue

        event_step = event.get("step")
        if event_step != step:
            continue
        key = (event_step, idx, event.get("kind"), json.dumps(event, sort_keys=True, default=str))
        if key in logged_event_ids:
            continue
        logged_event_ids.add(key)
        log.append("events", {"step": event_step, **{k: v for k, v in event.items() if k != "step"}})


def run_scenario(
    name: str,
    output_dir: Optional[Path] = None,
    overrides: Optional[Dict[str, Any]] = None,
    recreate_output: bool = True,
) -> Path:
    config = load_scenario_config(name, overrides=overrides)
    agents_config = load_agents_config(name, config)
    sim_cfg = config.get("simulation", {})
    steps = int(sim_cfg.get("steps", 50))
    output_cfg = config.get("output", {})

    results_base = Path(__file__).resolve().parents[1] / "experiments" / "results"
    if output_dir is None:
        run_id = output_cfg.get("run_id", name)
        if agents_config and agents_config.get("mode") == "labeled":
            run_id = output_cfg.get("run_id_labeled", f"{name}_labeled")
        elif agents_config and agents_config.get("mode") == "labeled_llm_guarded":
            run_id = output_cfg.get("run_id_labeled_llm_guarded", f"{name}_labeled_llm_guarded")
        if recreate_output:
            run_dir = EventLog.prepare_run_dir(results_base, run_id=run_id)
        else:
            run_dir = results_base / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
    else:
        run_dir = Path(output_dir)
        if recreate_output and run_dir.exists():
            import shutil
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)

    sim = build_simulator(config)
    team = build_agent_team(name, agents_config)
    log = EventLog(run_dir)

    peak_co2 = 0.0
    min_power_margin_w: Optional[float] = None
    anomaly_seen = False
    co2_above_threshold_step: Optional[int] = None
    co2_recovered_below_threshold_step: Optional[int] = None
    eps_boost_applied_step: Optional[int] = None
    power_recovered_above_critical_step: Optional[int] = None
    message_count = 0
    last_snap = None
    last_health = None
    logged_event_ids: set = set()
    was_power_critical = False
    station = sim if isinstance(sim, StationSimulator) else None

    for _ in range(steps):
        snap = sim.step()
        last_snap = snap
        peak_co2 = max(peak_co2, snap.co2_ppm)
        min_power_margin_w = (
            snap.power_margin_w
            if min_power_margin_w is None
            else min(min_power_margin_w, snap.power_margin_w)
        )
        health = compute_health_metrics(snap)
        last_health = health

        if health.power_status == HealthStatus.CRITICAL:
            was_power_critical = True
        elif was_power_critical and power_recovered_above_critical_step is None:
            power_recovered_above_critical_step = snap.step

        if station is not None:
            log.append("eps_telemetry", station.eps_telemetry_dict(snap.step))

        if snap.anomaly_flags:
            anomaly_seen = True
        if snap.co2_ppm > 1000.0 and co2_above_threshold_step is None:
            co2_above_threshold_step = snap.step
        if snap.co2_ppm < 1000.0 and co2_above_threshold_step is not None:
            if co2_recovered_below_threshold_step is None:
                co2_recovered_below_threshold_step = snap.step

        log.append("telemetry", snap.to_dict())
        log.append("health_metrics", health.to_dict())
        log.append("design_state", {"step": snap.step, **sim.get_design_state().to_dict()})
        _log_sim_events(log, sim, snap.step, logged_event_ids)

        if team is not None:
            obs = AgentObservation(step=snap.step, telemetry=snap, health=health)
            outcome = team.run_step(sim, obs)
            team.apply_outcome(sim, outcome)
            for msg in outcome.messages:
                log.append("messages", msg.to_dict())
                message_count += 1
            _log_sim_events(log, sim, snap.step, logged_event_ids)

    for event in sim.get_events():
        if event.get("kind") != EVENT_RECOVERY:
            continue
        command = event.get("command") or {}
        if command.get("kind") != "request_eps_boost":
            continue
        step = event.get("step")
        if step is not None and eps_boost_applied_step is None:
            eps_boost_applied_step = int(step)

    summary = {
            "scenario": name,
            "simulator": "mock_station",
            "agents_mode": (agents_config or {}).get("mode", "none"),
            "steps": steps,
            "peak_co2_ppm": round(peak_co2, 2),
            "final_co2_ppm": last_snap.co2_ppm if last_snap else None,
            "final_power_margin_w": last_snap.power_margin_w if last_snap else None,
            "min_power_margin_w": round(min_power_margin_w, 2) if min_power_margin_w is not None else None,
            "eps_boost_applied_step": eps_boost_applied_step,
            "power_recovered_above_critical_step": power_recovered_above_critical_step,
            "final_health": last_health.to_dict() if last_health else None,
            "anomaly_seen": anomaly_seen,
            "co2_above_threshold_step": co2_above_threshold_step,
            "co2_recovered_below_threshold_step": co2_recovered_below_threshold_step,
            "message_count": message_count,
            "design_change_count": sum(
                1 for e in sim.get_events() if "design_change" in str(e.get("kind", "")).lower()
            ),
    }

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
