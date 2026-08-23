"""N-sweep of plant_sim metabolism vs one ARS/OGS/WRS action, plus YAML knob overrides.

Survival stays off so occupant count N is an independent variable. This is not
the Streamlit run dashboard. Interactive knobs live in
``python3 -m tools.plant_sim_sensitivity_app`` (port 8502).

Left column is unconstrained demand (∝ N), not tank-limited consumption.
Middle column is nameplate of one action (inventory ignored). Column 3 is the
simulated tank Δ / step (WRS waits until urine+grey ≥ ``wrs_feed_trigger_l``).
Column 4 is the ending tank (initial + campaign Δ).
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

import matplotlib.pyplot as plt
import yaml
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from environment.ssos.eclss.plant_sim.config import PlantSimConfig
from environment.ssos.eclss.plant_sim.model import PlantModel
from environment.ssos.eclss.units import water_kg_to_l
from scenario.runner import agents_config_path, scenario_config_path

MODES = ("none", "ars", "ogs", "wrs")
_SUBSYSTEMS = ("ars", "ogs", "wrs")
PAIR_MODES = ("ars+ogs", "ars+wrs", "ogs+wrs")
ALL_MODE = "all"
# First figure still plots MODES only. Extra campaigns feed the combo grid below it.
SWEEP_MODES = MODES + PAIR_MODES + (ALL_MODE,)


def campaign_ops(mode: str) -> Tuple[str, ...]:
    """Subsystems fired each step. Order is always ARS → OGS → WRS."""
    if mode == "none":
        return ()
    if mode == ALL_MODE:
        return _SUBSYSTEMS
    parts = tuple(mode.split("+"))
    if any(part not in _SUBSYSTEMS for part in parts) or not parts:
        raise ValueError(f"unknown mode {mode!r}")
    return tuple(sub for sub in _SUBSYSTEMS if sub in parts)


@dataclass
class SweepRow:
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
    initial_co2_kg: float
    initial_o2_kg: float
    initial_water_l: float
    final_co2_kg: float
    final_o2_kg: float
    final_water_l: float

    def per_step(self) -> "SweepRow":
        m = max(1, self.metabolism_steps)
        ops = max(1, self.steps)
        return SweepRow(
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
            initial_co2_kg=self.initial_co2_kg,
            initial_o2_kg=self.initial_o2_kg,
            initial_water_l=self.initial_water_l,
            final_co2_kg=self.final_co2_kg,
            final_o2_kg=self.final_o2_kg,
            final_water_l=self.final_water_l,
        )


def load_ssos_yaml() -> tuple[Dict[str, Any], Dict[str, Any]]:
    scenario = yaml.safe_load(scenario_config_path("ssos_eclss_loop").read_text(encoding="utf-8"))
    agents = yaml.safe_load(agents_config_path("ssos_eclss_loop").read_text(encoding="utf-8")) or {}
    return scenario, agents


def _policy_goals(agents: Mapping[str, Any]) -> Dict[str, Any]:
    nested = (agents.get("actor") or {}).get("policy") if isinstance(agents.get("actor"), Mapping) else None
    if isinstance(nested, Mapping) and nested:
        return dict(nested)
    return dict((agents.get("policy") or {}))


def load_dynamics() -> tuple[Dict[str, Any], Dict[str, Any], PlantSimConfig, Dict[str, Any]]:
    """YAML → PlantSimConfig (the plant_sim dynamics object)."""
    scenario, agents = load_ssos_yaml()
    cfg = PlantSimConfig.from_scenario_config(scenario)
    return scenario, agents, cfg, _policy_goals(agents)


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
    return float(result["o2_generated_kg"]), water_kg_to_l(float(result["processed_water_kg"]))


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


def _wrs_feed_trigger_l(policy: Mapping[str, Any]) -> float:
    """Labeled ignition: skip WRS until urine+grey reaches this (liters)."""
    return float(policy.get("wrs_feed_trigger_l", 0.5))


def run_campaign(
    *,
    n: int,
    mode: str,
    steps: int,
    scenario: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> SweepRow:
    ops = campaign_ops(mode)
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
    wrs_trigger = _wrs_feed_trigger_l(policy)

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
            water_metab += water_kg_to_l(float(metab["water_consumed_kg"]))
        if "ars" in ops:
            result = model.run_ars(ars_goal)
            co2_ops += float(result.get("co2_removed_kg") or 0.0)
        if "ogs" in ops:
            result = model.run_ogs(ogs_water)
            o2_ops += float(result.get("o2_generated_kg") or 0.0)
            water_ops += water_kg_to_l(float(result.get("processed_water_kg") or 0.0)) - water_kg_to_l(
                float(result.get("water_regenerated_kg") or 0.0)
            )
        if "wrs" in ops:
            waste_l = float(model.state.urine_buffer_l) + float(model.state.grey_water_l)
            if waste_l + 1e-12 >= wrs_trigger:
                result = model.run_wrs(wrs_urine)
                water_ops -= float(result.get("recovered_water_l") or 0.0)

    o2_demand, co2_demand, water_demand = metabolism_demand_per_step(n, cfg)
    ogs_o2_np, ogs_water_np = ogs_nameplate(ogs_water, cfg)
    return SweepRow(
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
        initial_co2_kg=initial_co2,
        initial_o2_kg=initial_o2,
        initial_water_l=initial_water,
        final_co2_kg=model.state.cabin_co2_kg,
        final_o2_kg=model.state.available_o2_kg,
        final_water_l=model.state.product_water_l,
    )


def sweep(
    *,
    n_max: int,
    steps: int,
    scenario: Mapping[str, Any] | None = None,
    agents: Mapping[str, Any] | None = None,
) -> List[SweepRow]:
    if scenario is None or agents is None:
        scenario, agents = load_ssos_yaml()
    policy = _policy_goals(agents)
    rows: List[SweepRow] = []
    for n in range(1, int(n_max) + 1):
        for mode in SWEEP_MODES:
            rows.append(
                run_campaign(n=n, mode=mode, steps=steps, scenario=scenario, policy=policy)
            )
    return rows


MODE_COLORS = {"none": "#111111", "ars": "#c44e52", "ogs": "#55a868", "wrs": "#1f77b4"}
MODE_MARKERS = {"none": "o", "ars": "^", "ogs": "D", "wrs": "s"}
MODE_ALPHAS = {"none": 1.00, "ars": 0.80, "ogs": 0.60, "wrs": 0.40}
MODE_LABELS = {
    "none": "no ECLSS",
    "ars": "ARS only",
    "ogs": "OGS only",
    "wrs": "WRS only",
}
COMBO_COLORS = {
    "ars": MODE_COLORS["ars"],
    "ogs": MODE_COLORS["ogs"],
    "wrs": MODE_COLORS["wrs"],
    "ars+ogs": "#7b4173",
    "ars+wrs": "#e377c2",
    "ogs+wrs": "#17becf",
    "all": "#ff7f0e",
}
COMBO_MARKERS = {
    "ars": MODE_MARKERS["ars"],
    "ogs": MODE_MARKERS["ogs"],
    "wrs": MODE_MARKERS["wrs"],
    "ars+ogs": "v",
    "ars+wrs": "P",
    "ogs+wrs": "X",
    "all": "*",
}
COMBO_ALPHAS = {
    "ars": MODE_ALPHAS["ars"],
    "ogs": MODE_ALPHAS["ogs"],
    "wrs": MODE_ALPHAS["wrs"],
    "ars+ogs": 0.85,
    "ars+wrs": 0.75,
    "ogs+wrs": 0.65,
    "all": 1.00,
}
COMBO_LABELS = {
    "ars": "ARS only",
    "ogs": "OGS only",
    "wrs": "WRS only",
    "ars+ogs": "ARS + OGS",
    "ars+wrs": "ARS + WRS",
    "ogs+wrs": "OGS + WRS",
    "all": "ARS + OGS + WRS",
}
COMBO_RATE_COLUMNS = (
    ("1 subsystem action", ("ars", "ogs", "wrs"), "Simulated Δ tank / step"),
    ("2 subsystem actions", PAIR_MODES, "Simulated Δ tank / step"),
    ("All subsystems", (ALL_MODE,), "1 call each / step"),
)
COMBO_LEVEL_MODES = ("ars", "ogs", "wrs") + PAIR_MODES + (ALL_MODE,)

# Rows 0–2 share a tank-delta sign: + means that inventory went up (per step).
# Column 3 is the ending tank (initial + campaign Δ), not a per-step rate.
_RESOURCES = (
    ("Cabin CO2", "co2", "kg / step", "kg"),
    ("Available O2", "o2", "kg / step", "kg"),
    ("Product water", "water", "L / step", "L"),
)
_RATE_KINDS = ("metabolism", "ops", "net")
_COLUMNS = (
    ("Crew metabolism", "metabolism", "Unconstrained demand ∝ N"),
    ("One subsystem action", "ops", "Nameplate of 1 call (no inventory)"),
    ("Tank inventory", "net", "Simulated Δ tank / step"),
    ("Tank + initial", "level", "Ending tank = initial + (Δ tank/step × steps)"),
)
N_RATE_COLS = 3


def tank_effect(row: SweepRow, resource: str, kind: str) -> float:
    """Signed effect on the named tank.

    metabolism / ops / net are per-step (+ = inventory up).
    level is the ending tank: initial + (Δ tank/step × steps), not divided by steps.
    """
    if resource == "co2":
        if kind == "metabolism":
            return row.co2_demand_kg
        if kind == "ops":
            return -row.ars_nameplate_kg if row.mode == "ars" else 0.0
        if kind == "net":
            return row.co2_net_kg
        if kind == "level":
            return row.final_co2_kg
    if resource == "o2":
        if kind == "metabolism":
            return -row.o2_demand_kg
        if kind == "ops":
            return row.ogs_nameplate_o2_kg if row.mode == "ogs" else 0.0
        if kind == "net":
            return row.o2_net_kg
        if kind == "level":
            return row.final_o2_kg
    if resource == "water":
        if kind == "metabolism":
            return -row.water_demand_l
        if kind == "ops":
            if row.mode == "ogs":
                return -row.ogs_nameplate_water_l
            if row.mode == "wrs":
                return row.wrs_nameplate_l
            return 0.0
        if kind == "net":
            return row.water_net_l
        if kind == "level":
            return row.final_water_l
    raise ValueError(f"unknown resource {resource!r} or kind {kind!r}")


def initial_tank(row: SweepRow, resource: str) -> float:
    if resource == "co2":
        return row.initial_co2_kg
    if resource == "o2":
        return row.initial_o2_kg
    if resource == "water":
        return row.initial_water_l
    raise ValueError(f"unknown resource {resource!r}")


def _row_ylim(values: Sequence[float]) -> tuple[float, float]:
    """Pad a shared y-range; always include 0 so tank-up / tank-down stay comparable."""
    finite = [float(v) for v in values if math.isfinite(float(v))]
    if not finite:
        return (-0.1, 0.1)
    lo = min(min(finite), 0.0)
    hi = max(max(finite), 0.0)
    if lo == hi:
        pad = 0.1
        return (lo - pad, hi + pad)
    pad = 0.08 * (hi - lo)
    return (lo - pad, hi + pad)


def _row_series_values(
    per_step: Sequence[SweepRow],
    baseline: Sequence[SweepRow],
    resource: str,
) -> List[float]:
    values: List[float] = [0.0]
    for item in list(per_step) + list(baseline):
        for kind in _RATE_KINDS:
            values.append(tank_effect(item, resource, kind))
    return values


def make_sweep_figure(
    rows: Sequence[SweepRow],
    *,
    baseline_rows: Sequence[SweepRow] | None = None,
    yaml_n: int | None = None,
    title: str = "plant_sim sensitivity — survival off, 1 action per step",
) -> plt.Figure:
    """Build the 3×4 grid. Caller owns show/save/close.

    Columns 0–2 (metabolism / action / tank Δ) share one y-scale per row.
    Column 3 is ending tank = initial + (Δ tank/step × steps) and uses its own scale.
    """
    per_step = [row.per_step() for row in rows if row.mode in MODES]
    baseline = [row.per_step() for row in baseline_rows if row.mode in MODES] if baseline_rows else []
    n_cols = len(_COLUMNS)
    fig, axes = plt.subplots(3, n_cols, figsize=(18.6, 9.2), sharex=True)
    for row_i in range(3):
        axes[row_i, 1].sharey(axes[row_i, 0])
        axes[row_i, 2].sharey(axes[row_i, 0])

    for col, (col_title, kind, col_subtitle) in enumerate(_COLUMNS):
        axes[0, col].set_title(f"{col_title}\n{col_subtitle}", fontsize=10, pad=8)
        for row_i, (name, resource, rate_unit, level_unit) in enumerate(_RESOURCES):
            ax = axes[row_i, col]
            for mode in MODES:
                series = [item for item in per_step if item.mode == mode]
                if not series:
                    continue
                ax.plot(
                    [item.n for item in series],
                    [tank_effect(item, resource, kind) for item in series],
                    color=MODE_COLORS[mode],
                    linewidth=1.9,
                    marker=MODE_MARKERS[mode],
                    markersize=4.0 if mode in {"none", "wrs"} else 3.5,
                    label=MODE_LABELS[mode],
                    alpha=MODE_ALPHAS[mode],
                    zorder=2 + MODES.index(mode),
                )
            if baseline:
                for mode in MODES:
                    series = [item for item in baseline if item.mode == mode]
                    if not series:
                        continue
                    ax.plot(
                        [item.n for item in series],
                        [tank_effect(item, resource, kind) for item in series],
                        color=MODE_COLORS[mode],
                        linewidth=1.8,
                        linestyle=(0, (1.2, 1.6)),
                        marker="",
                        alpha=MODE_ALPHAS[mode],
                        zorder=6 + MODES.index(mode),
                    )
            if kind == "level":
                if per_step:
                    ax.axhline(
                        initial_tank(per_step[0], resource),
                        color="#444444",
                        linewidth=0.9,
                        linestyle=":",
                    )
            else:
                ax.axhline(0.0, color="#888888", linewidth=0.8)
            if yaml_n is not None:
                ax.axvline(float(yaml_n), color="#bbbbbb", linewidth=0.9, linestyle=":")
            ax.grid(True, alpha=0.3)
            ax.tick_params(axis="y", labelleft=True)
            if col == 0:
                ax.set_ylabel(f"{name}\n({rate_unit})")
            if col == n_cols - 1:
                ax.set_ylabel(f"{name}\n({level_unit})")
            if row_i == len(_RESOURCES) - 1:
                ax.set_xlabel("Occupants N")

    for row_i, (_name, resource, _rate_unit, _level_unit) in enumerate(_RESOURCES):
        lo, hi = _row_ylim(_row_series_values(per_step, baseline, resource))
        for col in range(N_RATE_COLS):
            axes[row_i, col].set_ylim(lo, hi)
            axes[row_i, col].tick_params(axis="y", labelleft=True)
        level_vals = [0.0]
        for item in list(per_step) + list(baseline):
            level_vals.append(tank_effect(item, resource, "level"))
            level_vals.append(initial_tank(item, resource))
        lo_l, hi_l = _row_ylim(level_vals)
        axes[row_i, N_RATE_COLS].set_ylim(lo_l, hi_l)
        axes[row_i, N_RATE_COLS].tick_params(axis="y", labelleft=True)

    handles = [
        Line2D(
            [0],
            [0],
            color=MODE_COLORS[mode],
            lw=2,
            marker=MODE_MARKERS[mode],
            markersize=5,
            alpha=MODE_ALPHAS[mode],
            label=MODE_LABELS[mode],
        )
        for mode in MODES
    ]
    if baseline:
        handles.append(
            Line2D([0], [0], color="#666666", lw=1.6, linestyle=":", label="YAML baseline")
        )
    handles.append(
        Line2D([0], [0], color="#444444", lw=0.9, linestyle=":", label="YAML initial (col 4)")
    )
    fig.legend(handles=handles, loc="upper center", ncol=6, frameon=False, bbox_to_anchor=(0.5, 0.98))
    fig.suptitle(title, y=1.02, fontsize=13)
    fig.text(
        0.5,
        -0.01,
        "Columns 1–3 share a per-step y-scale. Column 4 is ending tank = initial + (Δ tank/step × steps) "
        "(own scale; dotted gray = initial fill). Dotted colored = YAML baseline.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0.0, 0.02, 1.0, 0.94))
    for row_i in range(3):
        for col in range(n_cols):
            axes[row_i, col].tick_params(axis="y", labelleft=True)
    return fig


def _plot_combo_series(
    ax,
    items: Sequence[SweepRow],
    modes: Sequence[str],
    resource: str,
    kind: str,
    *,
    baseline: bool,
) -> None:
    for index, mode in enumerate(modes):
        series = [item for item in items if item.mode == mode]
        if not series:
            continue
        if baseline:
            ax.plot(
                [item.n for item in series],
                [tank_effect(item, resource, kind) for item in series],
                color=COMBO_COLORS[mode],
                linewidth=1.8,
                linestyle=(0, (1.2, 1.6)),
                marker="",
                alpha=COMBO_ALPHAS[mode],
                zorder=6 + index,
            )
            continue
        ax.plot(
            [item.n for item in series],
            [tank_effect(item, resource, kind) for item in series],
            color=COMBO_COLORS[mode],
            linewidth=1.9,
            marker=COMBO_MARKERS[mode],
            markersize=5.0 if mode == ALL_MODE else 3.5,
            label=COMBO_LABELS[mode],
            alpha=COMBO_ALPHAS[mode],
            zorder=2 + index,
        )


def make_combo_figure(
    rows: Sequence[SweepRow],
    *,
    baseline_rows: Sequence[SweepRow] | None = None,
    yaml_n: int | None = None,
    title: str = "plant_sim sensitivity — 1 / 2 / all subsystem actions",
) -> plt.Figure:
    """3×4 grid: 1-action, 2-action, all-three per-step Δ, then ending tank.

    Columns 0–2 share a per-step y-scale per row. Column 3 is campaign ending
    tank (not divided by steps), same convention as the first figure's right column.
    """
    allowed = set(COMBO_LEVEL_MODES)
    per_step = [row.per_step() for row in rows if row.mode in allowed]
    baseline = [row.per_step() for row in baseline_rows if row.mode in allowed] if baseline_rows else []
    n_cols = 4
    fig, axes = plt.subplots(3, n_cols, figsize=(18.6, 9.2), sharex=True)
    for row_i in range(3):
        axes[row_i, 1].sharey(axes[row_i, 0])
        axes[row_i, 2].sharey(axes[row_i, 0])

    for col, (col_title, modes, col_subtitle) in enumerate(COMBO_RATE_COLUMNS):
        axes[0, col].set_title(f"{col_title}\n{col_subtitle}", fontsize=10, pad=8)
        for row_i, (name, resource, rate_unit, _level_unit) in enumerate(_RESOURCES):
            ax = axes[row_i, col]
            _plot_combo_series(ax, per_step, modes, resource, "net", baseline=False)
            if baseline:
                _plot_combo_series(ax, baseline, modes, resource, "net", baseline=True)
            ax.axhline(0.0, color="#888888", linewidth=0.8)
            if yaml_n is not None:
                ax.axvline(float(yaml_n), color="#bbbbbb", linewidth=0.9, linestyle=":")
            ax.grid(True, alpha=0.3)
            ax.tick_params(axis="y", labelleft=True)
            if col == 0:
                ax.set_ylabel(f"{name}\n({rate_unit})")
            if row_i == len(_RESOURCES) - 1:
                ax.set_xlabel("Occupants N")

    axes[0, 3].set_title(
        "Tank + initial\nEnding tank = initial + (Δ tank/step × steps)",
        fontsize=10,
        pad=8,
    )
    for row_i, (name, resource, _rate_unit, level_unit) in enumerate(_RESOURCES):
        ax = axes[row_i, 3]
        _plot_combo_series(ax, per_step, COMBO_LEVEL_MODES, resource, "level", baseline=False)
        if baseline:
            _plot_combo_series(ax, baseline, COMBO_LEVEL_MODES, resource, "level", baseline=True)
        if per_step:
            ax.axhline(
                initial_tank(per_step[0], resource),
                color="#444444",
                linewidth=0.9,
                linestyle=":",
            )
        if yaml_n is not None:
            ax.axvline(float(yaml_n), color="#bbbbbb", linewidth=0.9, linestyle=":")
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis="y", labelleft=True)
        ax.set_ylabel(f"{name}\n({level_unit})")
        if row_i == len(_RESOURCES) - 1:
            ax.set_xlabel("Occupants N")

    for row_i, (_name, resource, _rate_unit, _level_unit) in enumerate(_RESOURCES):
        rate_vals = [0.0]
        for item in list(per_step) + list(baseline):
            rate_vals.append(tank_effect(item, resource, "net"))
        lo, hi = _row_ylim(rate_vals)
        for col in range(3):
            axes[row_i, col].set_ylim(lo, hi)
            axes[row_i, col].tick_params(axis="y", labelleft=True)
        level_vals = [0.0]
        for item in list(per_step) + list(baseline):
            level_vals.append(tank_effect(item, resource, "level"))
            level_vals.append(initial_tank(item, resource))
        lo_l, hi_l = _row_ylim(level_vals)
        axes[row_i, 3].set_ylim(lo_l, hi_l)
        axes[row_i, 3].tick_params(axis="y", labelleft=True)

    handles = [
        Line2D(
            [0],
            [0],
            color=COMBO_COLORS[mode],
            lw=2,
            marker=COMBO_MARKERS[mode],
            markersize=5,
            alpha=COMBO_ALPHAS[mode],
            label=COMBO_LABELS[mode],
        )
        for mode in COMBO_LEVEL_MODES
    ]
    if baseline:
        handles.append(
            Line2D([0], [0], color="#666666", lw=1.6, linestyle=":", label="YAML baseline")
        )
    handles.append(
        Line2D([0], [0], color="#444444", lw=0.9, linestyle=":", label="YAML initial (col 4)")
    )
    fig.legend(handles=handles, loc="upper center", ncol=5, frameon=False, bbox_to_anchor=(0.5, 0.98))
    fig.suptitle(title, y=1.02, fontsize=13)
    fig.text(
        0.5,
        -0.01,
        "Columns 1–3 are simulated Δ tank / step (1 / 2 / all subsystems called once; "
        "WRS waits for wrs_feed_trigger_l). "
        "Column 4 is ending tank after the campaign (not per-step). Dotted colored = YAML baseline.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0.0, 0.02, 1.0, 0.94))
    for row_i in range(3):
        for col in range(n_cols):
            axes[row_i, col].tick_params(axis="y", labelleft=True)
    return fig


def _plot_combo_series(
    ax,
    items: Sequence[SweepRow],
    modes: Sequence[str],
    resource: str,
    kind: str,
    *,
    baseline: bool,
) -> None:
    for index, mode in enumerate(modes):
        series = [item for item in items if item.mode == mode]
        if not series:
            continue
        if baseline:
            ax.plot(
                [item.n for item in series],
                [tank_effect(item, resource, kind) for item in series],
                color=COMBO_COLORS[mode],
                linewidth=1.8,
                linestyle=(0, (1.2, 1.6)),
                marker="",
                alpha=COMBO_ALPHAS[mode],
                zorder=6 + index,
            )
            continue
        ax.plot(
            [item.n for item in series],
            [tank_effect(item, resource, kind) for item in series],
            color=COMBO_COLORS[mode],
            linewidth=1.9,
            marker=COMBO_MARKERS[mode],
            markersize=5.0 if mode == ALL_MODE else 3.5,
            label=COMBO_LABELS[mode],
            alpha=COMBO_ALPHAS[mode],
            zorder=2 + index,
        )


def make_combo_figure(
    rows: Sequence[SweepRow],
    *,
    baseline_rows: Sequence[SweepRow] | None = None,
    yaml_n: int | None = None,
    title: str = "plant_sim sensitivity — 1 / 2 / all subsystem actions",
) -> plt.Figure:
    """3×4 grid: 1-action, 2-action, all-three per-step Δ, then ending tank.

    Columns 0–2 share a per-step y-scale per row. Column 3 is campaign ending
    tank (not divided by steps), same convention as the first figure's right column.
    """
    allowed = set(COMBO_LEVEL_MODES)
    per_step = [row.per_step() for row in rows if row.mode in allowed]
    baseline = [row.per_step() for row in baseline_rows if row.mode in allowed] if baseline_rows else []
    n_cols = 4
    fig, axes = plt.subplots(3, n_cols, figsize=(18.6, 9.2), sharex=True)
    for row_i in range(3):
        axes[row_i, 1].sharey(axes[row_i, 0])
        axes[row_i, 2].sharey(axes[row_i, 0])

    for col, (col_title, modes, col_subtitle) in enumerate(COMBO_RATE_COLUMNS):
        axes[0, col].set_title(f"{col_title}\n{col_subtitle}", fontsize=10, pad=8)
        for row_i, (name, resource, rate_unit, _level_unit) in enumerate(_RESOURCES):
            ax = axes[row_i, col]
            _plot_combo_series(ax, per_step, modes, resource, "net", baseline=False)
            if baseline:
                _plot_combo_series(ax, baseline, modes, resource, "net", baseline=True)
            ax.axhline(0.0, color="#888888", linewidth=0.8)
            if yaml_n is not None:
                ax.axvline(float(yaml_n), color="#bbbbbb", linewidth=0.9, linestyle=":")
            ax.grid(True, alpha=0.3)
            ax.tick_params(axis="y", labelleft=True)
            if col == 0:
                ax.set_ylabel(f"{name}\n({rate_unit})")
            if row_i == len(_RESOURCES) - 1:
                ax.set_xlabel("Occupants N")

    axes[0, 3].set_title(
        "Tank + initial\nEnding tank = initial + (Δ tank/step × steps)",
        fontsize=10,
        pad=8,
    )
    for row_i, (name, resource, _rate_unit, level_unit) in enumerate(_RESOURCES):
        ax = axes[row_i, 3]
        _plot_combo_series(ax, per_step, COMBO_LEVEL_MODES, resource, "level", baseline=False)
        if baseline:
            _plot_combo_series(ax, baseline, COMBO_LEVEL_MODES, resource, "level", baseline=True)
        if per_step:
            ax.axhline(
                initial_tank(per_step[0], resource),
                color="#444444",
                linewidth=0.9,
                linestyle=":",
            )
        if yaml_n is not None:
            ax.axvline(float(yaml_n), color="#bbbbbb", linewidth=0.9, linestyle=":")
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis="y", labelleft=True)
        ax.set_ylabel(f"{name}\n({level_unit})")
        if row_i == len(_RESOURCES) - 1:
            ax.set_xlabel("Occupants N")

    for row_i, (_name, resource, _rate_unit, _level_unit) in enumerate(_RESOURCES):
        rate_vals = [0.0]
        for item in list(per_step) + list(baseline):
            rate_vals.append(tank_effect(item, resource, "net"))
        lo, hi = _row_ylim(rate_vals)
        for col in range(3):
            axes[row_i, col].set_ylim(lo, hi)
            axes[row_i, col].tick_params(axis="y", labelleft=True)
        level_vals = [0.0]
        for item in list(per_step) + list(baseline):
            level_vals.append(tank_effect(item, resource, "level"))
            level_vals.append(initial_tank(item, resource))
        lo_l, hi_l = _row_ylim(level_vals)
        axes[row_i, 3].set_ylim(lo_l, hi_l)
        axes[row_i, 3].tick_params(axis="y", labelleft=True)

    handles = [
        Line2D(
            [0],
            [0],
            color=COMBO_COLORS[mode],
            lw=2,
            marker=COMBO_MARKERS[mode],
            markersize=5,
            alpha=COMBO_ALPHAS[mode],
            label=COMBO_LABELS[mode],
        )
        for mode in COMBO_LEVEL_MODES
    ]
    if baseline:
        handles.append(
            Line2D([0], [0], color="#666666", lw=1.6, linestyle=":", label="YAML baseline")
        )
    handles.append(
        Line2D([0], [0], color="#444444", lw=0.9, linestyle=":", label="YAML initial (col 4)")
    )
    fig.legend(handles=handles, loc="upper center", ncol=5, frameon=False, bbox_to_anchor=(0.5, 0.98))
    fig.suptitle(title, y=1.02, fontsize=13)
    fig.text(
        0.5,
        -0.01,
        "Columns 1–3 are simulated Δ tank / step (1 / 2 / all subsystems called once; "
        "WRS waits for wrs_feed_trigger_l). "
        "Column 4 is ending tank after the campaign (not per-step). Dotted colored = YAML baseline.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0.0, 0.02, 1.0, 0.94))
    for row_i in range(3):
        for col in range(n_cols):
            axes[row_i, col].tick_params(axis="y", labelleft=True)
    return fig


# Dotted paths that the sensitivity app exposes (scenario.yaml + labeled policy).
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
POLICY_KEYS = (
    "actor.policy.ars_goal.initial_co2_mass",
    "actor.policy.ogs_goal.input_water_mass",
    "actor.policy.wrs_goal.urine_volume",
    "actor.policy.wrs_feed_trigger_l",
)
SCENARIO_KEYS = STORAGE_KEYS + PLANT_SIM_KEYS
SENSITIVITY_KEYS = SCENARIO_KEYS + POLICY_KEYS
POLICY_GROUP = "Policy"


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
    SliderSpec("simulation.initial_co2_storage_kg", "initial_co2_storage_kg", "kg", "float", 0.0, 10.0, 0.05, "Initial storage"),
    SliderSpec("simulation.initial_o2_storage_kg", "initial_o2_storage_kg", "kg", "float", 0.0, 20.0, 0.02, "Initial storage"),
    SliderSpec("simulation.initial_product_water_l", "initial_product_water_l", "L", "float", 0.0, 200.0, 1.0, "Initial storage"),
    SliderSpec("plant_sim.time.step_seconds", "step_seconds", "s", "int", 300, 3600, 60, "Time"),
    SliderSpec("plant_sim.time.ars_operation_seconds", "ars_operation_seconds", "s", "int", 600, 7200, 60, "Time"),
    SliderSpec("plant_sim.time.ogs_operation_seconds", "ogs_operation_seconds", "s", "int", 300, 3600, 60, "Time"),
    SliderSpec("plant_sim.time.wrs_operation_seconds", "wrs_operation_seconds", "s", "int", 300, 3600, 60, "Time"),
    SliderSpec("plant_sim.crew.size", "crew.size", "person", "int", 1, 64, 1, "Crew"),
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
    SliderSpec("plant_sim.ogs.max_o2_kg_day", "ogs.max_o2_kg_day", "kg/day", "float", 0.1, 50.0, 0.05, "OGS / Sabatier"),
    SliderSpec("plant_sim.sabatier.conversion_efficiency", "sabatier.conversion_efficiency", "-", "float", 0.0, 1.0, 0.01, "OGS / Sabatier"),
    SliderSpec("plant_sim.wrs.urine_recovery", "wrs.urine_recovery", "-", "float", 0.0, 1.0, 0.01, "WRS"),
    SliderSpec("plant_sim.wrs.grey_recovery", "wrs.grey_recovery", "-", "float", 0.0, 1.0, 0.01, "WRS"),
    SliderSpec("plant_sim.wrs.max_feed_l_per_operation", "wrs.max_feed_l_per_operation", "L", "float", 0.1, 20.0, 0.1, "WRS"),
    SliderSpec(
        "actor.policy.ars_goal.initial_co2_mass",
        "ars_goal.initial_co2_mass",
        "kg",
        "float",
        0.1,
        6.0,
        0.05,
        POLICY_GROUP,
    ),
    SliderSpec(
        "actor.policy.ogs_goal.input_water_mass",
        "ogs_goal.input_water_mass",
        "kg",
        "float",
        0.01,
        1.0,
        0.01,
        POLICY_GROUP,
    ),
    SliderSpec(
        "actor.policy.wrs_goal.urine_volume",
        "wrs_goal.urine_volume",
        "L",
        "float",
        0.1,
        20.0,
        0.1,
        POLICY_GROUP,
    ),
    SliderSpec(
        "actor.policy.wrs_feed_trigger_l",
        "wrs_feed_trigger_l",
        "L",
        "float",
        0.0,
        20.0,
        0.1,
        POLICY_GROUP,
    ),
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
    scenario, agents = load_ssos_yaml()
    out: Dict[str, float] = {}
    for spec in SLIDER_SPECS:
        source = agents if spec.key in POLICY_KEYS else scenario
        raw = _nested_get(source, spec.key)
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


def apply_policy_overrides(
    agents: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> Dict[str, Any]:
    """Deep-copy agents.yaml and apply labeled_rule_base policy knobs. Does not write disk."""
    merged: Dict[str, Any] = deepcopy(dict(agents))
    for key, value in overrides.items():
        if key not in POLICY_KEYS:
            continue
        _nested_set(merged, key, value)
    return merged


def apply_sensitivity_overrides(
    scenario: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> Dict[str, Any]:
    """Deep-copy scenario.yaml and apply dotted-path knobs. Does not write disk."""
    merged: Dict[str, Any] = deepcopy(dict(scenario))
    for key, value in overrides.items():
        if key in POLICY_KEYS:
            continue
        if key not in SCENARIO_KEYS:
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
) -> Tuple[List[SweepRow], Dict[str, Any]]:
    if scenario is None or agents is None:
        scenario, agents = load_ssos_yaml()
    patched = apply_sensitivity_overrides(scenario, overrides or {})
    patched_agents = apply_policy_overrides(agents, overrides or {})
    PlantSimConfig.from_scenario_config(patched)  # fail fast on invalid knobs
    rows = sweep(n_max=n_max, steps=steps, scenario=patched, agents=patched_agents)
    return rows, patched


def sensitivity_figure(
    rows: Sequence[SweepRow],
    *,
    baseline_rows: Sequence[SweepRow] | None = None,
    yaml_n: int | None = None,
) -> Figure:
    return make_sweep_figure(
        rows,
        baseline_rows=baseline_rows,
        yaml_n=yaml_n,
        title="plant_sim sensitivity — not the run dashboard",
    )


def combo_sensitivity_figure(
    rows: Sequence[SweepRow],
    *,
    baseline_rows: Sequence[SweepRow] | None = None,
    yaml_n: int | None = None,
) -> Figure:
    return make_combo_figure(
        rows,
        baseline_rows=baseline_rows,
        yaml_n=yaml_n,
        title="plant_sim sensitivity — 1 / 2 / all subsystem actions",
    )
