"""Offline plant_sim cheatsheet: metabolism vs one ARS/OGS/WRS op per step.

This is not the Streamlit dashboard. It sweeps occupant count N with survival
disabled so N stays an independent variable.

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
from environment.ssos.eclss.plant_sim.model import PlantModel
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
        )


def load_ssos_yaml() -> tuple[Dict[str, Any], Dict[str, Any]]:
    scenario = yaml.safe_load(scenario_config_path("ssos_eclss_loop").read_text(encoding="utf-8"))
    agents = yaml.safe_load(agents_config_path("ssos_eclss_loop").read_text(encoding="utf-8")) or {}
    return scenario, agents


def _policy_goals(agents: Mapping[str, Any]) -> Dict[str, Any]:
    return dict((agents.get("policy") or {}))


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


def plot_cheatsheet(rows: Sequence[CheatsheetRow], png_path: Path) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    per_step = [row.per_step() for row in rows]
    colors = {"none": "#4c72b0", "ars": "#c44e52", "ogs": "#55a868", "wrs": "#8172b3"}
    styles = {"metabolism": "--", "ops": ":", "net": "-"}
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)

    panels = (
        (
            axes[0],
            "Cabin CO2 (kg / step)",
            "co2_metabolism_kg",
            "co2_ops_kg",
            "co2_net_kg",
            True,
        ),
        (
            axes[1],
            "Available O2 (kg / step)",
            "o2_metabolism_kg",
            "o2_ops_kg",
            "o2_net_kg",
            False,
        ),
        (
            axes[2],
            "Product water (L / step)",
            "water_metabolism_l",
            "water_ops_l",
            "water_net_l",
            False,
        ),
    )
    for ax, title, metab_key, ops_key, net_key, invert_ops in panels:
        for mode in MODES:
            series = [row for row in per_step if row.mode == mode]
            n_vals = [row.n for row in series]
            metab = [getattr(row, metab_key) for row in series]
            ops = [(-getattr(row, ops_key) if invert_ops else getattr(row, ops_key)) for row in series]
            net = [getattr(row, net_key) for row in series]
            color = colors[mode]
            ax.plot(n_vals, metab, styles["metabolism"], color=color, linewidth=1.6)
            ax.plot(n_vals, ops, styles["ops"], color=color, linewidth=1.6)
            ax.plot(n_vals, net, styles["net"], color=color, linewidth=1.8)
        ax.set_ylabel(title)
        ax.grid(True, alpha=0.3)
        ax.axhline(0.0, color="#999999", linewidth=0.8)

    axes[-1].set_xlabel("Occupants / operators (N)")
    color_handles = [Line2D([0], [0], color=colors[m], lw=2, label=m) for m in MODES]
    style_handles = [
        Line2D([0], [0], color="#333333", linestyle=styles["metabolism"], label="metabolism"),
        Line2D([0], [0], color="#333333", linestyle=styles["ops"], label="operation I/O"),
        Line2D([0], [0], color="#333333", linestyle=styles["net"], label="inventory net"),
    ]
    axes[0].legend(handles=color_handles + style_handles, ncol=4, loc="upper left", fontsize=8)
    fig.suptitle("plant_sim ops cheatsheet (survival off, 1 operation / step)")
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)
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
