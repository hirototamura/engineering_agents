"""Offline plant_sim cheatsheet: metabolism vs one ARS/OGS/WRS op per step.

This is not the Streamlit dashboard. It sweeps occupant count N with survival
disabled so N stays an independent variable.

Left column is **unconstrained demand** (∝ N), not tank-limited consumption —
otherwise O2 metabolism flattens once the 0.48 kg tank is empty.
Middle column is **nameplate of one action** (inventory ignored), so ARS/OGS/WRS
are flat vs N. The right column is the simulated tank, where those limits live.

Usage::

    python3 -m tools.plant_sim_ops_cheatsheet --n-max 8 --steps 36
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import matplotlib.pyplot as plt
import yaml
from matplotlib.lines import Line2D

from environment.ssos.eclss.plant_sim.config import PlantSimConfig
from environment.ssos.eclss.plant_sim.model import PlantModel, per_interval
from environment.ssos.eclss.plant_sim.stoichiometry import WATER_PER_O2
from scenario.runner import agents_config_path, scenario_config_path

MODES = ("none", "ars", "ogs", "wrs")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PNG = REPO_ROOT / "docs" / "en" / "memo" / "ssos_eclss_loop" / "figures" / "ops_cheatsheet.png"
DEFAULT_CSV = DEFAULT_PNG.with_suffix(".csv")


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


def metabolism_demand_per_step(n: int, plant: PlantSimConfig) -> tuple[float, float, float]:
    """Unconstrained crew demand this interval: (o2_kg, co2_kg, water_l). ∝ N."""
    factor = int(n) * plant.activity_factor
    o2 = per_interval(plant.o2_kg_day_person, plant.step_seconds) * factor
    co2 = per_interval(plant.co2_kg_day_person, plant.step_seconds) * factor
    water = per_interval(plant.potable_water_kg_day_person, plant.step_seconds) * factor
    return o2, co2, water


def ars_nameplate_kg(goal_co2_mass_kg: float, plant: PlantSimConfig) -> float:
    """One ARS action with infinite cabin CO2: capacity × goal scale. Independent of N."""
    scale = float(goal_co2_mass_kg) / plant.ars_reference_goal_co2_kg
    operation_capacity = per_interval(plant.ars_capacity_kg_day, plant.ars_operation_seconds)
    return operation_capacity * scale


def ogs_nameplate(input_water_mass_kg: float, plant: PlantSimConfig) -> tuple[float, float]:
    """One OGS action with infinite water tank: (o2_produced_kg, water_consumed_l)."""
    requested = float(input_water_mass_kg)
    max_o2 = per_interval(plant.ogs_max_o2_kg_day, plant.ogs_operation_seconds)
    max_water_by_capacity = max_o2 * WATER_PER_O2
    processed = min(requested, max_water_by_capacity)
    return processed / WATER_PER_O2, processed


def wrs_nameplate_l(requested_urine_l: float, plant: PlantSimConfig) -> float:
    """One WRS action assuming the requested urine is in the buffer. Independent of N.

    Grey water is not in the WRS goal payload; it is opportunistic from inventory
    and therefore belongs in the tank column, not the nameplate.
    """
    urine_feed = min(float(requested_urine_l), plant.wrs_max_feed_l_per_operation)
    return urine_feed * plant.wrs_urine_recovery


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
    ars_goal = float((policy.get("ars_goal") or {}).get("initial_co2_mass", cfg.ars_reference_goal_co2_kg))
    ogs_water = float((policy.get("ogs_goal") or {}).get("input_water_mass", 0.15))
    wrs_urine = float((policy.get("wrs_goal") or {}).get("urine_volume", 2.0))

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
        "Every panel uses the same sign: above zero = that tank increased. "
        "Left = demand ∝ N (O2 does not flatten when the tank is empty). "
        "Middle = one action's nameplate (flat vs N). Right = simulated tank.",
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
    args = parser.parse_args(list(argv) if argv is not None else None)
    rows = sweep(n_max=args.n_max, steps=args.steps)
    write_csv(args.csv, rows)
    plot_cheatsheet(rows, args.png)
    print(f"wrote {args.png}")
    print(f"wrote {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
