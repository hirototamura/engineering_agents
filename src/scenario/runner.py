"""Scenario runner — loads YAML and drives Mock ECLSS with EventLog output."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.event_log import EventLog
from environment.eclss_ops.design_state import DesignStateManager
from environment.protocol import AnomalySpec, SimulatorProtocol
from environment.ssos.mock_eclss import MockEclssSimulator
from environment.ssos.station_simulator import StationSimulator
from environment.ssos.eps_stack import EpsStack
from environment.ssos.mock_sarj import MockSarj
from scenario.agents.scrubber_degradation_team import ScrubberDegradationTeam

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
    from scenario.scrubber_degradation.scenario_run import SCENARIO_REGISTRY

    scenario = SCENARIO_REGISTRY.get(name)
    if scenario is None:
        raise ValueError(f"No registered scenario: {name}")
    return scenario.run(output_dir=output_dir, overrides=overrides, recreate_output=recreate_output)
