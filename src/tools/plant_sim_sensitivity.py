"""Apply scenario.yaml storage / plant_sim knobs to the ops cheatsheet sweep.

This is the non-UI core for the interactive sensitivity app. Survival stays off.
Crew water sinks are rescaled so urine + condensate + unrecoverable = potable.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from matplotlib.figure import Figure

from environment.ssos.eclss.plant_sim.config import PlantSimConfig
from tools.plant_sim_ops_cheatsheet import (
    CheatsheetRow,
    load_ssos_yaml,
    make_cheatsheet_figure,
    sweep,
)

# Dotted paths that the sensitivity app exposes (scenario.yaml).
STORAGE_KEYS = (
    "simulation.initial_co2_storage_kg",
    "simulation.initial_o2_storage_kg",
    "simulation.initial_product_water_l",
)
PLANT_SIM_KEYS = (
    "plant_sim.time.step_seconds",
    "plant_sim.time.ars_operation_seconds",
    "plant_sim.time.ogs_operation_seconds",
    "plant_sim.time.wrs_operation_seconds",
    "plant_sim.crew.size",
    "plant_sim.crew.activity_factor",
    "plant_sim.crew.co2_kg_day_person",
    "plant_sim.crew.o2_kg_day_person",
    "plant_sim.crew.potable_water_kg_day_person",
    "plant_sim.crew.urine_kg_day_person",
    "plant_sim.crew.condensate_kg_day_person",
    "plant_sim.crew.unrecoverable_water_kg_day_person",
    "plant_sim.ars.capacity_kg_day",
    "plant_sim.ars.capture_efficiency",
    "plant_sim.ars.reference_goal_co2_kg",
    "plant_sim.ogs.max_o2_kg_day",
    "plant_sim.sabatier.conversion_efficiency",
    "plant_sim.wrs.urine_recovery",
    "plant_sim.wrs.grey_recovery",
    "plant_sim.wrs.max_feed_l_per_operation",
)
SENSITIVITY_KEYS = STORAGE_KEYS + PLANT_SIM_KEYS


@dataclass(frozen=True)
class SliderSpec:
    key: str
    label: str
    unit: str
    kind: str  # "float" | "int"
    minimum: float
    maximum: float
    step: float
    group: str


SLIDER_SPECS: Tuple[SliderSpec, ...] = (
    SliderSpec("simulation.initial_co2_storage_kg", "initial_co2_storage_kg", "kg", "float", 0.0, 6.0, 0.05, "Initial storage"),
    SliderSpec("simulation.initial_o2_storage_kg", "initial_o2_storage_kg", "kg", "float", 0.0, 6.0, 0.02, "Initial storage"),
    SliderSpec("simulation.initial_product_water_l", "initial_product_water_l", "L", "float", 0.0, 200.0, 1.0, "Initial storage"),
    SliderSpec("plant_sim.time.step_seconds", "step_seconds", "s", "int", 300, 3600, 60, "Time"),
    SliderSpec("plant_sim.time.ars_operation_seconds", "ars_operation_seconds", "s", "int", 600, 7200, 60, "Time"),
    SliderSpec("plant_sim.time.ogs_operation_seconds", "ogs_operation_seconds", "s", "int", 300, 3600, 60, "Time"),
    SliderSpec("plant_sim.time.wrs_operation_seconds", "wrs_operation_seconds", "s", "int", 300, 3600, 60, "Time"),
    SliderSpec("plant_sim.crew.size", "crew.size", "person", "int", 1, 8, 1, "Crew"),
    SliderSpec("plant_sim.crew.activity_factor", "activity_factor", "-", "float", 0.0, 4.0, 0.1, "Crew"),
    SliderSpec("plant_sim.crew.co2_kg_day_person", "co2_kg_day_person", "kg/day/person", "float", 0.0, 3.0, 0.02, "Crew"),
    SliderSpec("plant_sim.crew.o2_kg_day_person", "o2_kg_day_person", "kg/day/person", "float", 0.0, 3.0, 0.02, "Crew"),
    SliderSpec("plant_sim.crew.potable_water_kg_day_person", "potable_water_kg_day_person", "kg/day/person", "float", 0.05, 6.0, 0.02, "Crew"),
    SliderSpec("plant_sim.crew.urine_kg_day_person", "urine_kg_day_person", "kg/day/person", "float", 0.0, 5.0, 0.02, "Crew"),
    SliderSpec("plant_sim.crew.condensate_kg_day_person", "condensate_kg_day_person", "kg/day/person", "float", 0.0, 5.0, 0.02, "Crew"),
    SliderSpec("plant_sim.crew.unrecoverable_water_kg_day_person", "unrecoverable_water_kg_day_person", "kg/day/person", "float", 0.0, 1.0, 0.01, "Crew"),
    SliderSpec("plant_sim.ars.capacity_kg_day", "ars.capacity_kg_day", "kg/day", "float", 0.1, 15.0, 0.1, "ARS"),
    SliderSpec("plant_sim.ars.capture_efficiency", "ars.capture_efficiency", "-", "float", 0.0, 1.0, 0.01, "ARS"),
    SliderSpec("plant_sim.ars.reference_goal_co2_kg", "ars.reference_goal_co2_kg", "kg", "float", 0.1, 6.0, 0.05, "ARS"),
    SliderSpec("plant_sim.ogs.max_o2_kg_day", "ogs.max_o2_kg_day", "kg/day", "float", 0.1, 20.0, 0.05, "OGS / Sabatier"),
    SliderSpec("plant_sim.sabatier.conversion_efficiency", "sabatier.conversion_efficiency", "-", "float", 0.0, 1.0, 0.01, "OGS / Sabatier"),
    SliderSpec("plant_sim.wrs.urine_recovery", "wrs.urine_recovery", "-", "float", 0.0, 1.0, 0.01, "WRS"),
    SliderSpec("plant_sim.wrs.grey_recovery", "wrs.grey_recovery", "-", "float", 0.0, 1.0, 0.01, "WRS"),
    SliderSpec("plant_sim.wrs.max_feed_l_per_operation", "wrs.max_feed_l_per_operation", "L", "float", 0.1, 20.0, 0.1, "WRS"),
)


def _nested_get(doc: Mapping[str, Any], dotted: str) -> Any:
    cur: Any = doc
    for key in dotted.split("."):
        cur = cur[key]
    return cur


def _nested_set(doc: MutableMapping[str, Any], dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    cur: MutableMapping[str, Any] = doc
    for key in keys[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[keys[-1]] = value


def yaml_defaults() -> Dict[str, float]:
    scenario, _agents = load_ssos_yaml()
    out: Dict[str, float] = {}
    for spec in SLIDER_SPECS:
        raw = _nested_get(scenario, spec.key)
        out[spec.key] = int(raw) if spec.kind == "int" else float(raw)
    return out


def close_crew_water(crew: MutableMapping[str, Any]) -> None:
    """Scale urine/condensate/unrecoverable so they sum to potable intake."""
    potable = float(crew["potable_water_kg_day_person"])
    urine = max(0.0, float(crew.get("urine_kg_day_person") or 0.0))
    condensate = max(0.0, float(crew.get("condensate_kg_day_person") or 0.0))
    unrec = max(0.0, float(crew.get("unrecoverable_water_kg_day_person") or 0.0))
    total = urine + condensate + unrec
    if potable <= 0.0:
        crew["potable_water_kg_day_person"] = 0.0
        crew["urine_kg_day_person"] = 0.0
        crew["condensate_kg_day_person"] = 0.0
        crew["unrecoverable_water_kg_day_person"] = 0.0
        return
    if total <= 0.0:
        crew["urine_kg_day_person"] = potable
        crew["condensate_kg_day_person"] = 0.0
        crew["unrecoverable_water_kg_day_person"] = 0.0
        return
    scale = potable / total
    crew["urine_kg_day_person"] = urine * scale
    crew["condensate_kg_day_person"] = condensate * scale
    crew["unrecoverable_water_kg_day_person"] = unrec * scale


def apply_sensitivity_overrides(
    scenario: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> Dict[str, Any]:
    """Deep-copy scenario.yaml and apply dotted-path knobs. Does not write disk."""
    merged: Dict[str, Any] = deepcopy(dict(scenario))
    for key, value in overrides.items():
        if key not in SENSITIVITY_KEYS:
            raise KeyError(f"unsupported sensitivity key {key!r}")
        _nested_set(merged, key, value)
    crew = dict((merged.get("plant_sim") or {}).get("crew") or {})
    if crew:
        if "size" in crew:
            crew["size"] = int(crew["size"])
            _nested_set(merged, "plant_sim.crew.size", crew["size"])
        close_crew_water(crew)
        _nested_set(merged, "plant_sim.crew.urine_kg_day_person", crew["urine_kg_day_person"])
        _nested_set(merged, "plant_sim.crew.condensate_kg_day_person", crew["condensate_kg_day_person"])
        _nested_set(merged, "plant_sim.crew.unrecoverable_water_kg_day_person", crew["unrecoverable_water_kg_day_person"])
    survival = dict((merged.get("plant_sim") or {}).get("survival") or {})
    survival["enabled"] = False
    _nested_set(merged, "plant_sim.survival.enabled", False)
    return merged


def run_sensitivity(
    overrides: Mapping[str, Any] | None = None,
    *,
    n_max: int = 8,
    steps: int = 20,
    scenario: Mapping[str, Any] | None = None,
    agents: Mapping[str, Any] | None = None,
) -> Tuple[List[CheatsheetRow], Dict[str, Any]]:
    if scenario is None or agents is None:
        scenario, agents = load_ssos_yaml()
    patched = apply_sensitivity_overrides(scenario, overrides or {})
    PlantSimConfig.from_scenario_config(patched)  # fail fast on invalid knobs
    rows = sweep(n_max=n_max, steps=steps, scenario=patched, agents=agents)
    return rows, patched


def sensitivity_figure(
    rows: Sequence[CheatsheetRow],
    *,
    baseline_rows: Sequence[CheatsheetRow] | None = None,
    yaml_n: int | None = None,
) -> Figure:
    return make_cheatsheet_figure(
        rows,
        baseline_rows=baseline_rows,
        yaml_n=yaml_n,
        title="plant_sim sensitivity — not the run dashboard",
    )
