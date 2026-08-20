"""Offline plant_sim cheatsheet: metabolism vs one ARS/OGS/WRS op per step.

This is not the Streamlit dashboard. It sweeps occupant count N with survival
disabled so N stays an independent variable.

Left column is **unconstrained demand** (∝ N), not tank-limited consumption —
otherwise O2 metabolism flattens once the 0.48 kg tank is empty.
Middle column is **nameplate of one action** (inventory ignored), so ARS/OGS/WRS
are flat vs N. The right column is the simulated tank, where those limits live.

Usage::

    python3 -m tools.plant_sim_ops_cheatsheet --n-max 8 --steps 36

Also writes `ops_cheatsheet_sources.md` / `.json` / `.png`: YAML paths, the loaded
`PlantSimConfig` (dynamics), the YAML formula, and the `PlantModel` probe that
the 3×3 actually plots.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import matplotlib.pyplot as plt
import yaml
from matplotlib.lines import Line2D

from environment.ssos.eclss.plant_sim.config import PlantSimConfig
from environment.ssos.eclss.plant_sim.model import PlantModel
from environment.ssos.eclss.plant_sim.stoichiometry import WATER_PER_O2
from scenario.runner import agents_config_path, scenario_config_path

MODES = ("none", "ars", "ogs", "wrs")
SECONDS_PER_DAY = 86400.0

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PNG = REPO_ROOT / "docs" / "en" / "memo" / "ssos_eclss_loop" / "figures" / "ops_cheatsheet.png"
DEFAULT_CSV = DEFAULT_PNG.with_suffix(".csv")
DEFAULT_SOURCES_MD = DEFAULT_PNG.with_name("ops_cheatsheet_sources.md")
DEFAULT_SOURCES_JSON = DEFAULT_PNG.with_name("ops_cheatsheet_sources.json")
DEFAULT_SOURCES_PNG = DEFAULT_PNG.with_name("ops_cheatsheet_sources.png")
SCENARIO_YAML_REL = "src/scenario/ssos_eclss_loop/scenario.yaml"
AGENTS_YAML_REL = "src/scenario/ssos_eclss_loop/agents.yaml"


@dataclass
class CheatsheetRow:
    n: int
    mode: str
    steps: int
    metabolism_steps: int
    co2_metabolism_kg: float
    co2_ops_kg: float
    co2_net_kg: float
    o2_metabolism_kg: float
    o2_ops_kg: float
    o2_net_kg: float
    water_metabolism_l: float
    water_ops_l: float
    water_net_l: float
    # Per-step unconstrained demand / nameplate (not divided in per_step()).
    co2_demand_kg: float
    o2_demand_kg: float
    water_demand_l: float
    ars_nameplate_kg: float
    ogs_nameplate_o2_kg: float
    ogs_nameplate_water_l: float
    wrs_nameplate_l: float

    def per_step(self) -> "CheatsheetRow":
        m = max(1, self.metabolism_steps)
        ops = max(1, self.steps)
        return CheatsheetRow(
            n=self.n,
            mode=self.mode,
            steps=self.steps,
            metabolism_steps=self.metabolism_steps,
            co2_metabolism_kg=self.co2_metabolism_kg / m,
            co2_ops_kg=self.co2_ops_kg / ops,
            co2_net_kg=self.co2_net_kg / m,
            o2_metabolism_kg=self.o2_metabolism_kg / m,
            o2_ops_kg=self.o2_ops_kg / ops,
            o2_net_kg=self.o2_net_kg / m,
            water_metabolism_l=self.water_metabolism_l / m,
            water_ops_l=self.water_ops_l / ops,
            water_net_l=self.water_net_l / m,
            co2_demand_kg=self.co2_demand_kg,
            o2_demand_kg=self.o2_demand_kg,
            water_demand_l=self.water_demand_l,
            ars_nameplate_kg=self.ars_nameplate_kg,
            ogs_nameplate_o2_kg=self.ogs_nameplate_o2_kg,
            ogs_nameplate_water_l=self.ogs_nameplate_water_l,
            wrs_nameplate_l=self.wrs_nameplate_l,
        )


def load_ssos_yaml() -> tuple[Dict[str, Any], Dict[str, Any]]:
    scenario = yaml.safe_load(scenario_config_path("ssos_eclss_loop").read_text(encoding="utf-8"))
    agents = yaml.safe_load(agents_config_path("ssos_eclss_loop").read_text(encoding="utf-8")) or {}
    return scenario, agents


def _policy_goals(agents: Mapping[str, Any]) -> Dict[str, Any]:
    return dict((agents.get("policy") or {}))


def load_dynamics() -> tuple[Dict[str, Any], Dict[str, Any], PlantSimConfig, Dict[str, Any]]:
    """YAML → PlantSimConfig (the plant_sim dynamics object)."""
    scenario, agents = load_ssos_yaml()
    cfg = PlantSimConfig.from_scenario_config(scenario)
    return scenario, agents, cfg, _policy_goals(agents)


def _yaml_get(doc: Mapping[str, Any], dotted: str) -> Any:
    cur: Any = doc
    for key in dotted.split("."):
        cur = cur[key]
    return cur


def metabolism_demand_per_step(n: int, plant: PlantSimConfig) -> tuple[float, float, float]:
    """Unconstrained crew demand this interval: (o2_kg, co2_kg, water_l). ∝ N.

    Values come from PlantModel (same formulas as advance_step), not a parallel copy.
    """
    cfg = replace(plant, crew_size=int(n), survival_enabled=False)
    model = PlantModel(cfg)
    headcount = int(n)
    return (
        model.per_person_o2_demand_kg() * headcount,
        model.per_person_co2_generated_kg() * headcount,
        model.per_person_water_demand_l() * headcount,
    )


def ars_nameplate_kg(goal_co2_mass_kg: float, plant: PlantSimConfig) -> float:
    """One ARS action with cabin CO2 treated as unlimited. Independent of N."""
    model = PlantModel(replace(plant, initial_cabin_co2_kg=1.0e6, survival_enabled=False))
    return float(model.run_ars(float(goal_co2_mass_kg))["co2_removed_kg"])


def ogs_nameplate(input_water_mass_kg: float, plant: PlantSimConfig) -> tuple[float, float]:
    """One OGS action with water tank treated as unlimited: (o2_kg, water_l)."""
    model = PlantModel(replace(plant, initial_product_water_l=1.0e6, survival_enabled=False))
    result = model.run_ogs(float(input_water_mass_kg))
    return float(result["o2_generated_kg"]), float(result["processed_water_kg"])


def wrs_nameplate_l(requested_urine_l: float, plant: PlantSimConfig) -> float:
    """One WRS action with the requested urine already in the buffer. Independent of N."""
    model = PlantModel(
        replace(
            plant,
            initial_urine_buffer_l=float(requested_urine_l),
            initial_grey_water_l=0.0,
            survival_enabled=False,
        )
    )
    return float(model.run_wrs(float(requested_urine_l))["recovered_water_l"])


def _policy_action_goals(policy: Mapping[str, Any], plant: PlantSimConfig) -> tuple[float, float, float]:
    ars_goal = float((policy.get("ars_goal") or {}).get("initial_co2_mass", plant.ars_reference_goal_co2_kg))
    ogs_water = float((policy.get("ogs_goal") or {}).get("input_water_mass", 0.15))
    wrs_urine = float((policy.get("wrs_goal") or {}).get("urine_volume", 2.0))
    return ars_goal, ogs_water, wrs_urine


def run_campaign(
    *,
    n: int,
    mode: str,
    steps: int,
    scenario: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> CheatsheetRow:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    merged = dict(scenario)
    plant = dict(merged.get("plant_sim") or {})
    crew = dict(plant.get("crew") or {})
    crew["size"] = int(n)
    plant["crew"] = crew
    plant["survival"] = {"enabled": False}
    merged["plant_sim"] = plant
    cfg = replace(PlantSimConfig.from_scenario_config(merged), survival_enabled=False, crew_size=int(n))
    model = PlantModel(cfg)
    ars_goal, ogs_water, wrs_urine = _policy_action_goals(policy, cfg)

    initial_co2 = model.state.cabin_co2_kg
    initial_o2 = model.state.available_o2_kg
    initial_water = model.state.product_water_l
    co2_metab = o2_metab = water_metab = 0.0
    co2_ops = o2_ops = water_ops = 0.0
    metabolism_steps = 0

    for step in range(steps):
        if step > 0:
            metab = model.advance_step()
            metabolism_steps += 1
            co2_metab += float(metab["co2_generated_kg"])
            o2_metab += float(metab["o2_consumed_kg"])
            water_metab += float(metab["water_consumed_kg"])
        if mode == "ars":
            result = model.run_ars(ars_goal)
            co2_ops += float(result.get("co2_removed_kg") or 0.0)
        elif mode == "ogs":
            result = model.run_ogs(ogs_water)
            o2_ops += float(result.get("o2_generated_kg") or 0.0)
            water_ops += float(result.get("processed_water_kg") or 0.0) - float(
                result.get("water_regenerated_kg") or 0.0
            )
        elif mode == "wrs":
            result = model.run_wrs(wrs_urine)
            water_ops -= float(result.get("recovered_water_l") or 0.0)

    o2_demand, co2_demand, water_demand = metabolism_demand_per_step(n, cfg)
    ogs_o2_np, ogs_water_np = ogs_nameplate(ogs_water, cfg)
    return CheatsheetRow(
        n=n,
        mode=mode,
        steps=steps,
        metabolism_steps=metabolism_steps,
        co2_metabolism_kg=co2_metab,
        co2_ops_kg=co2_ops,
        co2_net_kg=model.state.cabin_co2_kg - initial_co2,
        o2_metabolism_kg=o2_metab,
        o2_ops_kg=o2_ops,
        o2_net_kg=model.state.available_o2_kg - initial_o2,
        water_metabolism_l=water_metab,
        water_ops_l=water_ops,
        water_net_l=model.state.product_water_l - initial_water,
        co2_demand_kg=co2_demand,
        o2_demand_kg=o2_demand,
        water_demand_l=water_demand,
        ars_nameplate_kg=ars_nameplate_kg(ars_goal, cfg),
        ogs_nameplate_o2_kg=ogs_o2_np,
        ogs_nameplate_water_l=ogs_water_np,
        wrs_nameplate_l=wrs_nameplate_l(wrs_urine, cfg),
    )


def sweep(
    *,
    n_max: int,
    steps: int,
    scenario: Mapping[str, Any] | None = None,
    agents: Mapping[str, Any] | None = None,
) -> List[CheatsheetRow]:
    if scenario is None or agents is None:
        scenario, agents = load_ssos_yaml()
    policy = _policy_goals(agents)
    rows: List[CheatsheetRow] = []
    for n in range(1, int(n_max) + 1):
        for mode in MODES:
            rows.append(
                run_campaign(n=n, mode=mode, steps=steps, scenario=scenario, policy=policy)
            )
    return rows


def write_csv(path: Path, rows: Sequence[CheatsheetRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(rows[0]).keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row.per_step()))


MODE_COLORS = {"none": "#4c72b0", "ars": "#c44e52", "ogs": "#55a868", "wrs": "#8172b3"}
MODE_LABELS = {
    "none": "no ECLSS",
    "ars": "ARS only",
    "ogs": "OGS only",
    "wrs": "WRS only",
}

# Rows share a tank-delta sign: + means that inventory went up.
_RESOURCES = (
    ("Cabin CO2 (kg / step)", "co2"),
    ("Available O2 (kg / step)", "o2"),
    ("Product water (L / step)", "water"),
)
_COLUMNS = (
    ("Crew metabolism", "metabolism", "Unconstrained demand ∝ N"),
    ("One subsystem action", "ops", "Nameplate of 1 call (no inventory)"),
    ("Tank inventory", "net", "Simulated tank after both"),
)


def tank_effect(row: CheatsheetRow, resource: str, kind: str) -> float:
    """Signed per-step effect on the named tank (+ = inventory up).

    Metabolism uses unconstrained demand (not tank-limited consumption).
    Ops uses nameplate of one action (inventory ignored). Net stays simulated.
    """
    if resource == "co2":
        if kind == "metabolism":
            return row.co2_demand_kg
        if kind == "ops":
            return -row.ars_nameplate_kg if row.mode == "ars" else 0.0
        return row.co2_net_kg
    if resource == "o2":
        if kind == "metabolism":
            return -row.o2_demand_kg
        if kind == "ops":
            return row.ogs_nameplate_o2_kg if row.mode == "ogs" else 0.0
        return row.o2_net_kg
    if resource == "water":
        if kind == "metabolism":
            return -row.water_demand_l
        if kind == "ops":
            if row.mode == "ogs":
                return -row.ogs_nameplate_water_l
            if row.mode == "wrs":
                return row.wrs_nameplate_l
            return 0.0
        return row.water_net_l
    raise ValueError(f"unknown resource {resource!r} or kind {kind!r}")


def _fmt(value: float, digits: int = 6) -> str:
    return f"{value:.{digits}g}"


def build_source_report(
    *,
    scenario: Mapping[str, Any],
    agents: Mapping[str, Any],
    plant: PlantSimConfig,
    policy: Mapping[str, Any],
    rows: Sequence[CheatsheetRow],
) -> Dict[str, Any]:
    """Trace each plotted number back to YAML and PlantModel (dynamics)."""
    ars_goal, ogs_water, wrs_urine = _policy_action_goals(policy, plant)
    yaml_map = {
        "plant_sim.time.step_seconds": _yaml_get(scenario, "plant_sim.time.step_seconds"),
        "plant_sim.time.ars_operation_seconds": _yaml_get(scenario, "plant_sim.time.ars_operation_seconds"),
        "plant_sim.time.ogs_operation_seconds": _yaml_get(scenario, "plant_sim.time.ogs_operation_seconds"),
        "plant_sim.crew.activity_factor": _yaml_get(scenario, "plant_sim.crew.activity_factor"),
        "plant_sim.crew.co2_kg_day_person": _yaml_get(scenario, "plant_sim.crew.co2_kg_day_person"),
        "plant_sim.crew.o2_kg_day_person": _yaml_get(scenario, "plant_sim.crew.o2_kg_day_person"),
        "plant_sim.crew.potable_water_kg_day_person": _yaml_get(
            scenario, "plant_sim.crew.potable_water_kg_day_person"
        ),
        "plant_sim.ars.capacity_kg_day": _yaml_get(scenario, "plant_sim.ars.capacity_kg_day"),
        "plant_sim.ars.reference_goal_co2_kg": _yaml_get(scenario, "plant_sim.ars.reference_goal_co2_kg"),
        "plant_sim.ogs.max_o2_kg_day": _yaml_get(scenario, "plant_sim.ogs.max_o2_kg_day"),
        "plant_sim.wrs.urine_recovery": _yaml_get(scenario, "plant_sim.wrs.urine_recovery"),
        "plant_sim.wrs.max_feed_l_per_operation": _yaml_get(
            scenario, "plant_sim.wrs.max_feed_l_per_operation"
        ),
        "simulation.initial_co2_storage_kg": _yaml_get(scenario, "simulation.initial_co2_storage_kg"),
        "simulation.initial_o2_storage_kg": _yaml_get(scenario, "simulation.initial_o2_storage_kg"),
        "simulation.initial_product_water_l": _yaml_get(scenario, "simulation.initial_product_water_l"),
        "policy.ars_goal.initial_co2_mass": _yaml_get(agents, "policy.ars_goal.initial_co2_mass"),
        "policy.ogs_goal.input_water_mass": _yaml_get(agents, "policy.ogs_goal.input_water_mass"),
        "policy.wrs_goal.urine_volume": _yaml_get(agents, "policy.wrs_goal.urine_volume"),
    }
    dynamics = {
        "step_seconds": plant.step_seconds,
        "ars_operation_seconds": plant.ars_operation_seconds,
        "ogs_operation_seconds": plant.ogs_operation_seconds,
        "activity_factor": plant.activity_factor,
        "co2_kg_day_person": plant.co2_kg_day_person,
        "o2_kg_day_person": plant.o2_kg_day_person,
        "potable_water_kg_day_person": plant.potable_water_kg_day_person,
        "ars_capacity_kg_day": plant.ars_capacity_kg_day,
        "ars_reference_goal_co2_kg": plant.ars_reference_goal_co2_kg,
        "ogs_max_o2_kg_day": plant.ogs_max_o2_kg_day,
        "wrs_urine_recovery": plant.wrs_urine_recovery,
        "wrs_max_feed_l_per_operation": plant.wrs_max_feed_l_per_operation,
        "initial_cabin_co2_kg": plant.initial_cabin_co2_kg,
        "initial_o2_kg": plant.initial_o2_kg,
        "initial_product_water_l": plant.initial_product_water_l,
        "WATER_PER_O2": WATER_PER_O2,
    }
    probe_n1 = PlantModel(replace(plant, crew_size=1, survival_enabled=False, initial_o2_kg=1.0e6, initial_product_water_l=1.0e6)).advance_step()
    o2_pp, co2_pp, water_pp = metabolism_demand_per_step(1, plant)
    metabolism_by_n = {}
    for n in range(1, 9):
        o2, co2, water = metabolism_demand_per_step(n, plant)
        metabolism_by_n[str(n)] = {
            "o2_demand_kg": o2,
            "co2_generated_kg": co2,
            "water_demand_l": water,
            "yaml_formula_o2": n * plant.activity_factor * plant.o2_kg_day_person * plant.step_seconds / SECONDS_PER_DAY,
            "yaml_formula_co2": n * plant.activity_factor * plant.co2_kg_day_person * plant.step_seconds / SECONDS_PER_DAY,
            "yaml_formula_water": n * plant.activity_factor * plant.potable_water_kg_day_person * plant.step_seconds / SECONDS_PER_DAY,
        }
    ars_np = ars_nameplate_kg(ars_goal, plant)
    ogs_o2, ogs_h2o = ogs_nameplate(ogs_water, plant)
    wrs_np = wrs_nameplate_l(wrs_urine, plant)
    ars_formula = (
        plant.ars_capacity_kg_day
        * plant.ars_operation_seconds
        / SECONDS_PER_DAY
        * (ars_goal / plant.ars_reference_goal_co2_kg)
    )
    ogs_cap_o2 = plant.ogs_max_o2_kg_day * plant.ogs_operation_seconds / SECONDS_PER_DAY
    ogs_formula_o2 = min(ogs_water / WATER_PER_O2, ogs_cap_o2)
    ogs_formula_water = min(ogs_water, ogs_cap_o2 * WATER_PER_O2)
    wrs_formula = min(wrs_urine, plant.wrs_max_feed_l_per_operation) * plant.wrs_urine_recovery

    tank_rows = []
    for row in rows:
        if row.n not in (1, 4, 8) or row.mode not in MODES:
            continue
        stepped = row.per_step()
        tank_rows.append(
            {
                "n": row.n,
                "mode": row.mode,
                "co2_net_kg_per_step": stepped.co2_net_kg,
                "o2_net_kg_per_step": stepped.o2_net_kg,
                "water_net_l_per_step": stepped.water_net_l,
                "o2_consumed_kg_per_step": stepped.o2_metabolism_kg,
                "o2_demand_kg": stepped.o2_demand_kg,
            }
        )

    return {
        "files": {"scenario": SCENARIO_YAML_REL, "agents": AGENTS_YAML_REL},
        "yaml": yaml_map,
        "dynamics_plant_sim": dynamics,
        "crew_metabolism": {
            "formula": "N × activity_factor × rate_kg_day × step_seconds / 86400",
            "plant_model_advance_step_n1": {
                "o2_demand_kg": float(probe_n1["o2_demand_kg"]),
                "co2_generated_kg": float(probe_n1["co2_generated_kg"]),
                "water_demand_kg": float(probe_n1["water_demand_kg"]),
            },
            "per_person": {"o2_kg": o2_pp, "co2_kg": co2_pp, "water_l": water_pp},
            "by_n": metabolism_by_n,
        },
        "one_subsystem_action": {
            "ars": {
                "yaml_goal": ars_goal,
                "formula": "capacity_kg_day × ars_operation_seconds / 86400 × (initial_co2_mass / reference_goal_co2_kg)",
                "yaml_formula_kg": ars_formula,
                "plant_model_run_ars_unconstrained_kg": ars_np,
            },
            "ogs": {
                "yaml_input_water_mass": ogs_water,
                "formula": "min(input_water_mass, ogs_max_o2_kg_day × ogs_operation_seconds / 86400 × WATER_PER_O2)",
                "yaml_formula_o2_kg": ogs_formula_o2,
                "yaml_formula_water_kg": ogs_formula_water,
                "plant_model_run_ogs_unconstrained_o2_kg": ogs_o2,
                "plant_model_run_ogs_unconstrained_water_kg": ogs_h2o,
            },
            "wrs": {
                "yaml_urine_volume": wrs_urine,
                "formula": "min(urine_volume, max_feed_l_per_operation) × urine_recovery",
                "yaml_formula_l": wrs_formula,
                "plant_model_run_wrs_requested_urine_l": wrs_np,
            },
        },
        "tank_inventory": {
            "initial_from_yaml": {
                "cabin_co2_kg": plant.initial_cabin_co2_kg,
                "available_o2_kg": plant.initial_o2_kg,
                "product_water_l": plant.initial_product_water_l,
            },
            "note": (
                "Right column is PlantModel (final − initial) / metabolism_steps "
                "with survival off and one action per step. O2 consumption saturates "
                "when available_o2_kg hits 0."
            ),
            "samples": tank_rows,
        },
    }


def format_source_report_md(report: Mapping[str, Any]) -> str:
    y = report["yaml"]
    d = report["dynamics_plant_sim"]
    m = report["crew_metabolism"]
    ops = report["one_subsystem_action"]
    tank = report["tank_inventory"]
    lines = [
        "# plant_sim cheatsheet — YAML → Dynamics → plotted value",
        "",
        f"- Scenario YAML: `{report['files']['scenario']}`",
        f"- Agents YAML: `{report['files']['agents']}`",
        "- Dynamics: `PlantSimConfig.from_scenario_config` + `PlantModel` (`environment.ssos.eclss.plant_sim`)",
        "",
        "`mock_dynamics` in the same YAML is the LoopMock backend. This cheatsheet does not use it.",
        "",
        "## 1. YAML loaded into PlantSimConfig",
        "",
        "| YAML path | YAML value | Dynamics field | loaded |",
        "| --- | ---: | --- | ---: |",
    ]
    mapping = [
        ("plant_sim.time.step_seconds", "step_seconds"),
        ("plant_sim.time.ars_operation_seconds", "ars_operation_seconds"),
        ("plant_sim.time.ogs_operation_seconds", "ogs_operation_seconds"),
        ("plant_sim.crew.activity_factor", "activity_factor"),
        ("plant_sim.crew.o2_kg_day_person", "o2_kg_day_person"),
        ("plant_sim.crew.co2_kg_day_person", "co2_kg_day_person"),
        ("plant_sim.crew.potable_water_kg_day_person", "potable_water_kg_day_person"),
        ("plant_sim.ars.capacity_kg_day", "ars_capacity_kg_day"),
        ("plant_sim.ars.reference_goal_co2_kg", "ars_reference_goal_co2_kg"),
        ("plant_sim.ogs.max_o2_kg_day", "ogs_max_o2_kg_day"),
        ("plant_sim.wrs.urine_recovery", "wrs_urine_recovery"),
        ("plant_sim.wrs.max_feed_l_per_operation", "wrs_max_feed_l_per_operation"),
        ("simulation.initial_co2_storage_kg", "initial_cabin_co2_kg"),
        ("simulation.initial_o2_storage_kg", "initial_o2_kg"),
        ("simulation.initial_product_water_l", "initial_product_water_l"),
    ]
    for yaml_path, field in mapping:
        lines.append(
            f"| `{yaml_path}` | {y[yaml_path]} | `{field}` | {d[field]} |"
        )
    lines.extend(
        [
            f"| `{AGENTS_YAML_REL}` `policy.ars_goal.initial_co2_mass` | {y['policy.ars_goal.initial_co2_mass']} | ARS goal | {ops['ars']['yaml_goal']} |",
            f"| `{AGENTS_YAML_REL}` `policy.ogs_goal.input_water_mass` | {y['policy.ogs_goal.input_water_mass']} | OGS request | {ops['ogs']['yaml_input_water_mass']} |",
            f"| `{AGENTS_YAML_REL}` `policy.wrs_goal.urine_volume` | {y['policy.wrs_goal.urine_volume']} | WRS request | {ops['wrs']['yaml_urine_volume']} |",
            "",
            "## 2. Crew metabolism (left column)",
            "",
            f"Formula (same as `PlantModel.advance_step`): `{m['formula']}`",
            "",
            f"PlantModel probe N=1 (oversized tanks): O2 demand `{m['plant_model_advance_step_n1']['o2_demand_kg']}`, "
            f"CO2 generated `{m['plant_model_advance_step_n1']['co2_generated_kg']}`, "
            f"water demand `{m['plant_model_advance_step_n1']['water_demand_kg']}` kg.",
            "",
            "| N | YAML formula O2 | PlantModel / plot O2 | YAML formula CO2 | plot CO2 | YAML formula water | plot water |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for n in range(1, 9):
        item = m["by_n"][str(n)]
        lines.append(
            f"| {n} | {_fmt(item['yaml_formula_o2'])} | {_fmt(item['o2_demand_kg'])} | "
            f"{_fmt(item['yaml_formula_co2'])} | {_fmt(item['co2_generated_kg'])} | "
            f"{_fmt(item['yaml_formula_water'])} | {_fmt(item['water_demand_l'])} |"
        )
    ars = ops["ars"]
    ogs = ops["ogs"]
    wrs = ops["wrs"]
    lines.extend(
        [
            "",
            "## 3. One subsystem action (middle column)",
            "",
            "Probes call `PlantModel.run_ars` / `run_ogs` / `run_wrs` with inventory large enough not to bind.",
            "",
            "| Machine | YAML + formula | YAML numeric | PlantModel probe (plotted) |",
            "| --- | --- | ---: | ---: |",
            f"| ARS CO2 removed | `{ars['formula']}` | {_fmt(ars['yaml_formula_kg'])} | {_fmt(ars['plant_model_run_ars_unconstrained_kg'])} |",
            f"| OGS O2 produced | `{ogs['formula']}` | {_fmt(ogs['yaml_formula_o2_kg'])} | {_fmt(ogs['plant_model_run_ogs_unconstrained_o2_kg'])} |",
            f"| OGS water used | same min() as water mass | {_fmt(ogs['yaml_formula_water_kg'])} | {_fmt(ogs['plant_model_run_ogs_unconstrained_water_kg'])} |",
            f"| WRS water recovered | `{wrs['formula']}` | {_fmt(wrs['yaml_formula_l'])} | {_fmt(wrs['plant_model_run_wrs_requested_urine_l'])} |",
            "",
            f"WATER_PER_O2 (stoichiometry, not YAML) = `{d['WATER_PER_O2']}`.",
            "",
            "## 4. Tank inventory (right column)",
            "",
            tank["note"],
            "",
            "| YAML path | initial tank |",
            "| --- | ---: |",
            f"| `simulation.initial_co2_storage_kg` | {tank['initial_from_yaml']['cabin_co2_kg']} kg cabin CO2 |",
            f"| `simulation.initial_o2_storage_kg` | {tank['initial_from_yaml']['available_o2_kg']} kg O2 |",
            f"| `simulation.initial_product_water_l` | {tank['initial_from_yaml']['product_water_l']} L water |",
            "",
            "| N | mode | ΔCO2 / step | ΔO2 / step | Δwater / step | O2 consumed (tank-limited) | O2 demand |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for sample in tank["samples"]:
        lines.append(
            f"| {sample['n']} | {sample['mode']} | {_fmt(sample['co2_net_kg_per_step'])} | "
            f"{_fmt(sample['o2_net_kg_per_step'])} | {_fmt(sample['water_net_l_per_step'])} | "
            f"{_fmt(sample['o2_consumed_kg_per_step'])} | {_fmt(sample['o2_demand_kg'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_source_report(path_md: Path, path_json: Path, report: Mapping[str, Any]) -> str:
    text = format_source_report_md(report)
    path_md.parent.mkdir(parents=True, exist_ok=True)
    path_md.write_text(text, encoding="utf-8")
    path_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return text


def plot_source_table(report: Mapping[str, Any], png_path: Path) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    y = report["yaml"]
    d = report["dynamics_plant_sim"]
    m = report["crew_metabolism"]["per_person"]
    ops = report["one_subsystem_action"]
    tank = report["tank_inventory"]["initial_from_yaml"]
    rows = [
        ["Crew O2 demand / person / step", "plant_sim.crew.o2_kg_day_person", str(y["plant_sim.crew.o2_kg_day_person"]), "o2_kg_day_person", f"{d['o2_kg_day_person']} × {d['step_seconds']}/86400", _fmt(m["o2_kg"])],
        ["Crew CO2 / person / step", "plant_sim.crew.co2_kg_day_person", str(y["plant_sim.crew.co2_kg_day_person"]), "co2_kg_day_person", f"{d['co2_kg_day_person']} × {d['step_seconds']}/86400", _fmt(m["co2_kg"])],
        ["Crew water / person / step", "plant_sim.crew.potable_water_kg_day_person", str(y["plant_sim.crew.potable_water_kg_day_person"]), "potable_water_kg_day_person", f"{d['potable_water_kg_day_person']} × {d['step_seconds']}/86400", _fmt(m["water_l"])],
        ["ARS nameplate kg / action", "plant_sim.ars.capacity_kg_day + agents ars_goal", f"{y['plant_sim.ars.capacity_kg_day']} ; goal {y['policy.ars_goal.initial_co2_mass']}", "run_ars unconstrained", f"{d['ars_capacity_kg_day']} × {d['ars_operation_seconds']}/86400 × goal/ref", _fmt(ops["ars"]["plant_model_run_ars_unconstrained_kg"])],
        ["OGS nameplate O2 kg / action", "plant_sim.ogs.max_o2_kg_day + agents ogs_goal", f"{y['plant_sim.ogs.max_o2_kg_day']} ; water {y['policy.ogs_goal.input_water_mass']}", "run_ogs unconstrained", "min(request, capacity × WATER_PER_O2)", _fmt(ops["ogs"]["plant_model_run_ogs_unconstrained_o2_kg"])],
        ["WRS nameplate L / action", "plant_sim.wrs.urine_recovery + agents wrs_goal", f"{y['plant_sim.wrs.urine_recovery']} ; urine {y['policy.wrs_goal.urine_volume']}", "run_wrs requested urine", f"min({y['policy.wrs_goal.urine_volume']}, {y['plant_sim.wrs.max_feed_l_per_operation']}) × {y['plant_sim.wrs.urine_recovery']}", _fmt(ops["wrs"]["plant_model_run_wrs_requested_urine_l"])],
        ["Tank initial cabin CO2", "simulation.initial_co2_storage_kg", str(y["simulation.initial_co2_storage_kg"]), "initial_cabin_co2_kg", "PlantModel start state", _fmt(tank["cabin_co2_kg"])],
        ["Tank initial O2", "simulation.initial_o2_storage_kg", str(y["simulation.initial_o2_storage_kg"]), "initial_o2_kg", "PlantModel start state", _fmt(tank["available_o2_kg"])],
        ["Tank initial water", "simulation.initial_product_water_l", str(y["simulation.initial_product_water_l"]), "initial_product_water_l", "PlantModel start state", _fmt(tank["product_water_l"])],
    ]
    fig, ax = plt.subplots(figsize=(16.5, 7.2))
    ax.axis("off")
    ax.set_title("YAML → PlantSimConfig / PlantModel → cheatsheet values", fontsize=13, pad=12)
    table = ax.table(
        cellText=rows,
        colLabels=["Plotted quantity", "YAML path", "YAML value", "Dynamics", "Formula", "Value"],
        loc="center",
        cellLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1.0, 1.55)
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_facecolor("#e8eef4")
            cell.set_text_props(weight="bold")
        elif row % 2 == 0:
            cell.set_facecolor("#f7f7f7")
    fig.text(
        0.5,
        0.04,
        "Left column of the 3×3 is N × per-person demand. Middle column is the nameplate row. "
        "Right column uses these initial tanks and saturates when empty.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0.0, 0.08, 1.0, 1.0))
    fig.savefig(png_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def plot_cheatsheet(rows: Sequence[CheatsheetRow], png_path: Path) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    per_step = [row.per_step() for row in rows]
    fig, axes = plt.subplots(3, 3, figsize=(13.5, 9.2), sharex=True, sharey="row")

    for col, (col_title, kind, col_subtitle) in enumerate(_COLUMNS):
        axes[0, col].set_title(f"{col_title}\n{col_subtitle}", fontsize=10, pad=8)
        for row_i, (ylabel, resource) in enumerate(_RESOURCES):
            ax = axes[row_i, col]
            for mode in MODES:
                series = [item for item in per_step if item.mode == mode]
                if not series:
                    continue
                n_vals = [item.n for item in series]
                y_vals = [tank_effect(item, resource, kind) for item in series]
                ax.plot(
                    n_vals,
                    y_vals,
                    color=MODE_COLORS[mode],
                    linewidth=1.9,
                    marker="o",
                    markersize=3.5,
                    label=MODE_LABELS[mode],
                )
            ax.axhline(0.0, color="#888888", linewidth=0.8)
            ax.grid(True, alpha=0.3)
            if col == 0:
                ax.set_ylabel(ylabel)
            if row_i == len(_RESOURCES) - 1:
                ax.set_xlabel("Occupants N")

    handles = [
        Line2D([0], [0], color=MODE_COLORS[mode], lw=2, marker="o", markersize=4, label=MODE_LABELS[mode])
        for mode in MODES
    ]
    fig.legend(handles=handles, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.98))
    fig.suptitle(
        "plant_sim cheatsheet — survival off, 1 action per step",
        y=1.02,
        fontsize=13,
    )
    fig.text(
        0.5,
        -0.01,
        "Left = demand ∝ N from PlantModel.advance_step (YAML crew rates × dt/86400). "
        "Middle = PlantModel.run_ars/ogs/wrs nameplate (inventory ignored). "
        "Right = simulated tank from simulation.initial_* YAML. See ops_cheatsheet_sources.md.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0.0, 0.02, 1.0, 0.94))
    fig.savefig(png_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write plant_sim ops cheatsheet PNG/CSV")
    parser.add_argument("--n-max", type=int, default=8)
    parser.add_argument("--steps", type=int, default=36)
    parser.add_argument("--png", type=Path, default=DEFAULT_PNG)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--sources-md", type=Path, default=DEFAULT_SOURCES_MD)
    parser.add_argument("--sources-json", type=Path, default=DEFAULT_SOURCES_JSON)
    parser.add_argument("--sources-png", type=Path, default=DEFAULT_SOURCES_PNG)
    args = parser.parse_args(list(argv) if argv is not None else None)
    scenario, agents, plant, policy = load_dynamics()
    rows = sweep(
        n_max=args.n_max,
        steps=args.steps,
        scenario=scenario,
        agents=agents,
    )
    write_csv(args.csv, rows)
    plot_cheatsheet(rows, args.png)
    report = build_source_report(
        scenario=scenario, agents=agents, plant=plant, policy=policy, rows=rows
    )
    text = write_source_report(args.sources_md, args.sources_json, report)
    plot_source_table(report, args.sources_png)
    print(text)
    print(f"wrote {args.png}")
    print(f"wrote {args.csv}")
    print(f"wrote {args.sources_md}")
    print(f"wrote {args.sources_json}")
    print(f"wrote {args.sources_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
