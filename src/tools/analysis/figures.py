"""Publication-style matplotlib figures, rendered to inline SVG.

Every figure returns an SVG string so the report is a single file with no asset
directory to keep in sync. Figures share one restrained style: no chart junk, no
gradients, axis labels always carry units, and every panel is self-describing so
it can be lifted out of the report and still be read.

The renderers take flat rows (as produced by
:mod:`tools.analysis.experiments`) rather than an intermediate object, so a
figure can be regenerated from a saved dataset without re-running anything.
"""

from __future__ import annotations

import io
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from tools.analysis.loop_dynamics import ARCHETYPES, AxisControllability, ChainDynamics  # noqa: E402
from tools.analysis.statistics import (  # noqa: E402
    KaplanMeierCurve,
    LogisticFit,
    central_difference,
    fit_logistic_response,
)

INK = "#1b1f24"
MUTED = "#6b7280"
GRID = "#dfe3e8"
ACCENT = "#1f6feb"
WARM = "#d1442f"
GREEN = "#2f855a"
AMBER = "#b7791f"
VIOLET = "#6b46c1"

SUBSPACE_COLOR = {"capacity": ACCENT, "action": WARM, "policy": AMBER, "topology": VIOLET}


def _style(ax: plt.Axes, *, xlabel: str = "", ylabel: str = "", title: str = "") -> None:
    ax.set_facecolor("white")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8.5, length=3)
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.9)
    ax.set_axisbelow(True)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9, color=INK)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9, color=INK)
    if title:
        ax.set_title(title, fontsize=10, color=INK, loc="left", pad=8)


def to_svg(fig: Figure) -> str:
    """Render a figure to an inline SVG fragment and close it."""

    buffer = io.StringIO()
    fig.savefig(buffer, format="svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    svg = buffer.getvalue()
    start = svg.find("<svg")
    return svg[start:] if start >= 0 else svg


def _col(rows: Sequence[Mapping[str, Any]], key: str) -> np.ndarray:
    return np.array([row.get(key) for row in rows], dtype=object)


def _num_col(rows: Sequence[Mapping[str, Any]], key: str) -> np.ndarray:
    out = []
    for row in rows:
        value = row.get(key)
        out.append(float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else math.nan)
    return np.array(out, dtype=float)


# --------------------------------------------------------------------------- #
# F1 physics validity
# --------------------------------------------------------------------------- #
def fig_mass_balance(rows: Sequence[Mapping[str, Any]]) -> str:
    """Ledger residuals across every run: the simulator's conservation check.

    Nothing downstream is meaningful if the plant does not conserve mass, so
    this is reported before any result. The physics gate recomputes each
    ledger independently of the state it audits.
    """

    keys = [("residual_o2_kg", "O2 ledger (kg)", ACCENT),
            ("residual_co2_kg", "CO2 ledger (kg)", WARM),
            ("residual_water_l", "water ledger (L)", GREEN)]
    tolerance = 2e-6
    floor = 1e-15

    fig, ax = plt.subplots(figsize=(7.0, 2.4))
    labels: List[str] = []
    for index, (key, label, color) in enumerate(keys):
        values = _num_col(rows, key)
        values = values[np.isfinite(values)]
        worst = float(values.max()) if values.size else math.nan
        labels.append(label)
        y = len(keys) - 1 - index
        if not math.isfinite(worst):
            continue
        if worst <= 0.0:
            ax.plot([floor], [y], marker="o", markersize=8, color=color, zorder=4)
            ax.annotate("exactly 0", (floor, y), textcoords="offset points",
                        xytext=(13, 0), va="center", fontsize=8, color=INK)
        else:
            ax.plot([worst], [y], marker="o", markersize=8, color=color, zorder=4)
            if worst <= tolerance:
                caption = f"{worst:.0e}  ({tolerance / worst:,.0f}x inside tolerance)"
            else:
                caption = f"{worst:.0e}  ({worst / tolerance:,.0f}x over tolerance)"
            ax.annotate(caption, (worst, y), textcoords="offset points", xytext=(13, 0),
                        va="center", fontsize=8, color=INK)
        ax.hlines(y, floor, max(worst, floor), color=color, linewidth=1.0, alpha=0.35)

    ax.axvline(tolerance, color=INK, linewidth=1.2, linestyle="--", zorder=5)
    ax.annotate(f"gate tolerance\n{tolerance:g}", (tolerance, len(keys) - 0.55),
                textcoords="offset points", xytext=(6, 0), fontsize=7.5, color=INK,
                va="top")
    ax.set_xscale("log")
    ax.set_xlim(floor / 3, tolerance * 40)
    ax.set_ylim(-0.6, len(keys) - 0.15)
    ax.set_yticks(np.arange(len(keys))[::-1])
    ax.set_yticklabels(labels, fontsize=9)
    _style(ax, xlabel="worst |residual| over every run (log scale)",
           title="Mass-balance residuals versus the physics-gate tolerance")
    return to_svg(fig)


# --------------------------------------------------------------------------- #
# F2 phase diagram
# --------------------------------------------------------------------------- #
def fig_phase_diagram(
    rows: Sequence[Mapping[str, Any]],
    *,
    x_key: str = "rho_ars",
    y_key: str = "rho_ogs",
    value_key: str = "survival_fraction",
) -> str:
    """Survival over the two binding coverage axes, with the feasibility edge."""

    xs = sorted({float(r[x_key]) for r in rows if isinstance(r.get(x_key), (int, float))})
    ys = sorted({float(r[y_key]) for r in rows if isinstance(r.get(y_key), (int, float))})
    if len(xs) < 2 or len(ys) < 2:
        fig, ax = plt.subplots(figsize=(6.6, 2.4))
        _style(ax, title="Response surface needs at least a 2x2 grid")
        return to_svg(fig)
    grid = np.full((len(ys), len(xs)), np.nan)
    x_index = {v: i for i, v in enumerate(xs)}
    y_index = {v: i for i, v in enumerate(ys)}
    for row in rows:
        x, y, v = row.get(x_key), row.get(y_key), row.get(value_key)
        if not all(isinstance(t, (int, float)) for t in (x, y, v)):
            continue
        grid[y_index[float(y)], x_index[float(x)]] = float(v)

    fig, (ax, cax) = plt.subplots(
        1, 2, figsize=(7.4, 4.4), gridspec_kw={"width_ratios": [24, 1]}
    )
    mesh = ax.pcolormesh(
        np.array(xs), np.array(ys), grid,
        cmap="RdYlGn", vmin=0.0, vmax=1.0, shading="nearest",
    )
    contour = ax.contour(
        np.array(xs), np.array(ys), grid,
        levels=[0.5, 0.999], colors=[INK, GREEN], linewidths=[1.4, 1.2],
        linestyles=["--", "-"],
    )
    ax.clabel(contour, fmt={0.5: "50%", 0.999: "full crew"}, fontsize=7.5)
    ax.axvline(1.0, color=MUTED, linewidth=0.9, linestyle=":")
    ax.axhline(1.0, color=MUTED, linewidth=0.9, linestyle=":")
    ax.plot([min(xs)], [min(ys)], marker="o", markersize=7, color=INK, zorder=6)
    ax.annotate("shipped\nbaseline", (min(xs), min(ys)), textcoords="offset points",
                xytext=(12, 10), fontsize=8, color=INK)
    ax.set_xscale("log")
    ax.set_yscale("log")
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_formatter(matplotlib.ticker.FuncFormatter(
            lambda v, _pos: f"{v:g}"
        ))
        axis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ticks = [0.1, 0.2, 0.5, 1.0, 2.0]
    ax.set_xticks([t for t in ticks if min(xs) <= t <= max(xs)])
    ax.set_yticks([t for t in ticks if min(ys) <= t <= max(ys)])
    _style(ax,
           xlabel=r"ARS coverage $\rho_{ARS}$  (CO2 removal capacity / crew CO2 output)",
           ylabel=r"OGS coverage $\rho_{OGS}$"
                  "\n(O2 generation / crew O2 demand)",
           title="Survival phase diagram over the two binding capacity axes")
    bar = fig.colorbar(mesh, cax=cax)
    bar.set_label("crew surviving (fraction of 50)", fontsize=8.5, color=INK)
    bar.ax.tick_params(colors=MUTED, labelsize=8)
    return to_svg(fig)


# --------------------------------------------------------------------------- #
# F3 criticality
# --------------------------------------------------------------------------- #
def fig_criticality(
    profiles: Mapping[str, Tuple[Sequence[float], Sequence[float]]],
    fits: Mapping[str, LogisticFit],
) -> str:
    """Survival response and its derivative along each coverage axis.

    The plant is deterministic, so the order parameter's *derivative* -- not a
    variance over replicates -- is what peaks at a transition. The peak locates
    the critical coverage and its height is the susceptibility.
    """

    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.2))
    colors = {"ARS (CO2 removal)": ACCENT, "OGS (O2 generation)": WARM,
              "crew scaling": VIOLET}
    for name, (xs, ys) in profiles.items():
        color = colors.get(name, MUTED)
        order = np.argsort(np.asarray(xs, dtype=float))
        x = np.asarray(xs, dtype=float)[order]
        y = np.asarray(ys, dtype=float)[order]
        axes[0].plot(x, y, marker="o", markersize=3.5, linewidth=1.4, color=color, label=name)
        fit = fits.get(name)
        if fit is not None and math.isfinite(fit.x0):
            dense = np.linspace(x.min(), x.max(), 300)
            axes[0].plot(dense, fit.predict(dense), linewidth=1.0, linestyle="--",
                         color=color, alpha=0.55)
            axes[0].axvline(fit.x0, color=color, linewidth=0.8, linestyle=":", alpha=0.7)
        cx, slope = central_difference(x, y)
        if cx.size:
            axes[1].plot(cx, np.abs(slope), marker="o", markersize=3.5,
                         linewidth=1.4, color=color, label=name)
    axes[0].axvline(1.0, color=MUTED, linewidth=0.9, linestyle=":")
    axes[0].set_ylim(-0.05, 1.08)
    _style(axes[0], xlabel=r"coverage ratio $\rho$ (dimensionless)",
           ylabel="surviving crew fraction",
           title="Order parameter")
    if profiles:
        axes[0].legend(fontsize=7.5, frameon=False, loc="lower right")
    axes[1].axvline(1.0, color=MUTED, linewidth=0.9, linestyle=":")
    _style(axes[1], xlabel=r"coverage ratio $\rho$ (dimensionless)",
           ylabel=r"susceptibility $|\,d S / d\rho\,|$",
           title="Susceptibility")
    return to_svg(fig)


# --------------------------------------------------------------------------- #
# F4 controllability
# --------------------------------------------------------------------------- #
def fig_controllability(
    controls: Sequence[AxisControllability],
    magnitude_share: Mapping[str, float],
) -> str:
    """What each axis can do, next to what the shipped designer actually moves."""

    ordered = list(controls)
    if not ordered:
        fig, ax = plt.subplots(figsize=(6.6, 2.4))
        _style(ax, title="No one-at-a-time sweep in this dataset")
        return to_svg(fig)

    fig, axes = plt.subplots(
        1, 2, figsize=(7.8, 3.4), gridspec_kw={"width_ratios": [3, 2]}
    )
    names = [c.axis.replace("_", " ") for c in ordered]
    gains = [c.gain for c in ordered]
    colors = [SUBSPACE_COLOR.get(c.subspace, MUTED) for c in ordered]
    positions = np.arange(len(ordered))[::-1]
    axes[0].barh(positions, gains, height=0.62, color=colors, zorder=3)
    axes[0].set_yticks(positions)
    axes[0].set_yticklabels(names, fontsize=8)
    for pos, gain in zip(positions, gains):
        axes[0].text(gain + max(gains) * 0.015, pos, f"{gain:.3f}",
                     va="center", fontsize=7.5, color=INK)
    axes[0].set_xlim(0, max(gains) * 1.22 if max(gains) > 0 else 1.0)
    _style(axes[0], xlabel=r"controllability  $|\,dS/d\ln x\,|$  (crew fraction per e-fold)",
           title="Controllability of each actuation axis")
    handles = [
        plt.Line2D([], [], color=color, linewidth=6, label=name)
        for name, color in SUBSPACE_COLOR.items() if name != "topology"
    ]
    axes[0].legend(handles=handles, fontsize=7.5, frameon=False, loc="lower right",
                   title="subspace", title_fontsize=7.5)

    subspaces = [s for s in ("capacity", "action", "policy")]
    shares = [float(magnitude_share.get(s, 0.0)) for s in subspaces]
    axes[1].bar(np.arange(len(subspaces)), shares, width=0.5,
                color=[SUBSPACE_COLOR[s] for s in subspaces], zorder=3)
    for i, share in enumerate(shares):
        axes[1].text(i, share + 0.03, f"{share * 100:.0f}%", ha="center",
                     fontsize=8.5, color=INK)
    axes[1].set_xticks(np.arange(len(subspaces)))
    axes[1].set_xticklabels(subspaces, fontsize=8.5)
    axes[1].set_ylim(0, 1.15)
    _style(axes[1], ylabel="share of design-step magnitude",
           title="Where the shipped designer moves")
    return to_svg(fig)


# --------------------------------------------------------------------------- #
# F5 loop trajectories
# --------------------------------------------------------------------------- #
def fig_loop_dynamics(chains: Sequence[ChainDynamics]) -> str:
    """Order parameters of the closed loop, iteration by iteration."""

    fig, axes = plt.subplots(1, 4, figsize=(9.6, 2.9))
    palette = [ACCENT, WARM, GREEN, VIOLET, AMBER]
    step_values: List[float] = []
    for index, chain in enumerate(chains):
        color = palette[index % len(palette)]
        label = f"n={chain.length}"
        it = [s.iteration for s in chain.states]
        axes[0].plot(it, [s.displacement for s in chain.states], marker="o",
                     markersize=3.5, linewidth=1.4, color=color, label=label)
        steps = [s.step_norm for s in chain.states[1:]]
        axes[1].plot(it[1:], steps, marker="o",
                     markersize=3.5, linewidth=1.4, color=color, label=label)
        step_values.extend(steps)
        turn = [(s.iteration, s.turning_cosine) for s in chain.states
                if s.turning_cosine is not None]
        if turn:
            axes[2].plot([t[0] for t in turn], [t[1] for t in turn], marker="o",
                         markersize=3.5, linewidth=1.4, color=color, label=label)
        axes[3].plot(it, [s.survival_fraction for s in chain.states], marker="o",
                     markersize=3.5, linewidth=1.4, color=color, label=label)

    _style(axes[0], xlabel="iteration k", ylabel=r"$\|d_k - d_0\|$  (log units)",
           title="Displacement")
    # A constant step size would otherwise be drawn as float noise around an
    # offset, which reads as structure that is not there.
    if step_values:
        centre = float(np.mean(step_values))
        spread = float(np.max(step_values) - np.min(step_values))
        if spread < max(centre * 1e-3, 1e-9):
            axes[1].set_ylim(0.0, centre * 1.6)
            axes[1].annotate(f"constant at {centre:.3f}", (0.5, 0.16),
                             xycoords="axes fraction", fontsize=7.5, color=MUTED,
                             ha="center")
    axes[1].ticklabel_format(axis="y", style="plain", useOffset=False)
    _style(axes[1], xlabel="iteration k", ylabel=r"$\|d_k - d_{k-1}\|$",
           title="Step size")
    axes[2].set_ylim(-1.15, 1.15)
    axes[2].annotate("+1 = straight march", (0.5, 0.12), xycoords="axes fraction",
                     fontsize=7.5, color=MUTED, ha="center")
    axes[2].axhline(0.0, color=MUTED, linewidth=0.8, linestyle=":")
    _style(axes[2], xlabel="iteration k", ylabel=r"$\cos\theta_k$",
           title="Turning angle")
    axes[3].set_ylim(-0.05, 1.05)
    _style(axes[3], xlabel="iteration k", ylabel="surviving crew fraction",
           title="Outcome")
    if chains:
        axes[3].legend(fontsize=7.5, frameon=False, loc="center right")
    return to_svg(fig)


# --------------------------------------------------------------------------- #
# F6 archetypes
# --------------------------------------------------------------------------- #
def fig_archetypes(distribution: Mapping[str, float], n_chains: int) -> str:
    """Share of chains in each trajectory archetype."""

    fig, ax = plt.subplots(figsize=(7.0, 2.2))
    left = 0.0
    palette = {"frozen": MUTED, "saturating": WARM, "converging": GREEN,
               "overshooting": AMBER, "oscillating": VIOLET}
    for name in ARCHETYPES:
        share = float(distribution.get(name, 0.0))
        if share <= 0:
            continue
        ax.barh([0], [share], left=left, height=0.5, color=palette[name], zorder=3)
        ax.text(left + share / 2, 0, f"{name}\n{share * 100:.0f}%", ha="center",
                va="center", fontsize=8.5, color="white")
        left += share
    ax.set_xlim(0, 1)
    ax.set_yticks([])
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    _style(ax, xlabel=f"share of design chains (n={n_chains})",
           title="Trajectory archetypes of the closed loop")
    return to_svg(fig)


# --------------------------------------------------------------------------- #
# F7 survival analysis
# --------------------------------------------------------------------------- #
def fig_survival_curves(
    curves: Mapping[str, KaplanMeierCurve],
    annotation: str = "",
) -> str:
    """Kaplan-Meier time-to-first-crew-loss, grouped by coverage regime."""

    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    palette = [WARM, AMBER, GREEN, ACCENT]
    for index, (label, curve) in enumerate(curves.items()):
        color = palette[index % len(palette)]
        times = np.array(curve.times, dtype=float) / 3600.0
        surv = np.array(curve.survival, dtype=float)
        ax.step(times, surv, where="post", linewidth=1.6, color=color,
                label=f"{label}  (n={curve.n}, events={curve.n_events})")
        censored = curve.n - curve.n_events
        if censored and surv.size:
            ax.plot([times[-1]], [surv[-1]], marker="|", markersize=9,
                    color=color, markeredgewidth=1.6)
    ax.set_ylim(-0.03, 1.05)
    _style(ax, xlabel="mission time (hours)",
           ylabel="probability the crew is still intact",
           title="Time to first crew loss, by coverage regime")
    ax.legend(fontsize=7.5, frameon=False, loc="lower left")
    return to_svg(fig)


# --------------------------------------------------------------------------- #
# F8 cost of survival
# --------------------------------------------------------------------------- #
def fig_pareto(
    rows: Sequence[Mapping[str, Any]],
    budgets: Mapping[str, float],
) -> str:
    """Station footprint against survival, with the declared budget ceiling."""

    mass = _num_col(rows, "total_mass_kg")
    survival = _num_col(rows, "survival_fraction")
    cost = _num_col(rows, "total_cost_musd")
    ok = np.isfinite(mass) & np.isfinite(survival) & np.isfinite(cost)
    mass, survival, cost = mass[ok], survival[ok], cost[ok]

    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.3))
    scatter = axes[0].scatter(mass, survival, c=cost, cmap="viridis", s=18,
                              edgecolors="none", zorder=3)
    mass_budget = float(budgets.get("max_total_mass_kg", math.nan))
    if math.isfinite(mass_budget):
        axes[0].axvline(mass_budget, color=WARM, linewidth=1.3, linestyle="--", zorder=4)
        axes[0].text(mass_budget, 0.5, f" mass budget\n {mass_budget:g} kg",
                     fontsize=7.5, color=WARM, va="center")
    axes[0].set_ylim(-0.05, 1.08)
    _style(axes[0], xlabel="station mass (kg)", ylabel="surviving crew fraction",
           title="Survival against station mass")
    bar = fig.colorbar(scatter, ax=axes[0])
    bar.set_label("total cost (MUSD)", fontsize=8, color=INK)
    bar.ax.tick_params(colors=MUTED, labelsize=7.5)

    full = survival >= 1.0
    if full.any():
        cheapest = float(mass[full].min())
        axes[1].scatter(mass[~full], cost[~full], s=16, color=GRID, edgecolors="none",
                        label="crew lost", zorder=3)
        axes[1].scatter(mass[full], cost[full], s=20, color=GREEN, edgecolors="none",
                        label="full survival", zorder=4)
        axes[1].axvline(cheapest, color=GREEN, linewidth=1.2, linestyle=":", zorder=5)
        axes[1].annotate(f"lightest surviving\ndesign: {cheapest:.0f} kg",
                         (cheapest, float(np.nanmax(cost)) * 0.75),
                         textcoords="offset points", xytext=(8, 0), fontsize=7.5,
                         color=GREEN)
    if math.isfinite(mass_budget):
        axes[1].axvline(mass_budget, color=WARM, linewidth=1.3, linestyle="--", zorder=5)
    cost_budget = float(budgets.get("max_total_cost_musd", math.nan))
    if math.isfinite(cost_budget):
        axes[1].axhline(cost_budget, color=WARM, linewidth=1.3, linestyle="--", zorder=5)
    _style(axes[1], xlabel="station mass (kg)", ylabel="total cost (MUSD)",
           title="Feasible box against surviving designs")
    if full.any():
        axes[1].legend(fontsize=7.5, frameon=False, loc="upper left")
    return to_svg(fig)


# --------------------------------------------------------------------------- #
# F9 predictive law
# --------------------------------------------------------------------------- #
def fig_predictive_law(
    observed: Sequence[float],
    predictions: Mapping[str, Sequence[float]],
    scores: Mapping[str, Mapping[str, float]],
) -> str:
    """Observed against predicted survival for each candidate law."""

    names = list(predictions)
    if not names:
        raise ValueError("predictive law figure needs at least one model")
    fig, axes = plt.subplots(1, len(names), figsize=(2.5 * len(names), 2.8), squeeze=False)
    try:
        obs = np.asarray(list(observed), dtype=float)
        for index, name in enumerate(names):
            ax = axes[0][index]
            pred = np.asarray(list(predictions[name]), dtype=float)
            ax.plot([0, 1], [0, 1], linewidth=0.9, color=MUTED, linestyle=":")
            ax.scatter(pred, obs, s=14, color=ACCENT, alpha=0.65, edgecolors="none", zorder=3)
            stats = scores.get(name, {})
            r2 = stats.get("r_squared", math.nan)
            bacc = stats.get("balanced_accuracy", math.nan)
            ax.text(0.04, 0.95, f"$R^2$ = {r2:.3f}\nbal. acc. = {bacc:.3f}",
                    transform=ax.transAxes, fontsize=7.5, va="top", color=INK)
            ax.set_xlim(-0.05, 1.05)
            ax.set_ylim(-0.05, 1.05)
            _style(ax, xlabel="predicted", ylabel="observed" if index == 0 else "",
                   title=name)
        return to_svg(fig)
    except Exception:
        plt.close(fig)
        raise


# --------------------------------------------------------------------------- #
# F10 saturation evidence
# --------------------------------------------------------------------------- #
def fig_saturation(rows: Sequence[Mapping[str, Any]]) -> str:
    """Why enlarging the O2 request changes nothing.

    Takes the one-at-a-time sweep of the OGS request payload with the hardware
    held at its shipped size. As the request grows, the share of operations the
    plant reports as limited by ``ogs_capacity`` saturates at one and the
    surviving crew does not move: the plant delivers the minimum of request and
    nameplate, so everything above the nameplate is discarded on arrival.
    """

    payload = [r for r in rows if r.get("axis") == "ogs_action_water_mass"]
    payload.sort(key=lambda r: float(r.get("multiplier") or 0.0))
    if not payload:
        fig, ax = plt.subplots(figsize=(6.6, 2.4))
        _style(ax, title="No OGS payload sweep in this dataset")
        return to_svg(fig)

    mult = _num_col(payload, "multiplier")
    clipped = _num_col(payload, "limited_oxygen_generation.ogs_capacity")
    clipped = np.nan_to_num(clipped, nan=0.0)
    survival = _num_col(payload, "survival_fraction")

    fig, ax = plt.subplots(figsize=(6.8, 3.2))
    ax.plot(mult, clipped, marker="o", markersize=4.5, linewidth=1.6, color=WARM,
            label="operations clipped by ogs_capacity", zorder=3)
    ax.plot(mult, survival, marker="s", markersize=4.5, linewidth=1.6, color=ACCENT,
            label="surviving crew fraction", zorder=3)
    ax.axvline(1.0, color=MUTED, linewidth=0.9, linestyle=":")
    ax.annotate("shipped\nrequest", (1.0, 0.5), textcoords="offset points",
                xytext=(7, 0), fontsize=7.5, color=MUTED, va="center")
    ax.set_xscale("log")
    ax.set_xticks([0.5, 1, 2, 4, 10])
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _p: f"{v:g}x"))
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_ylim(-0.05, 1.1)
    _style(ax, xlabel="OGS request payload, relative to the shipped value",
           ylabel="fraction",
           title="OGS request payload versus capacity limiting and survival")
    ax.legend(fontsize=8, frameon=False, loc="center right")
    return to_svg(fig)


# --------------------------------------------------------------------------- #
# F11 crew scaling cross-check
# --------------------------------------------------------------------------- #
def fig_crew_scaling(
    capacity_profile: Tuple[Sequence[float], Sequence[float]],
    crew_profile: Tuple[Sequence[float], Sequence[float]],
) -> str:
    """The same order parameter reached from numerator and denominator."""

    fig, ax = plt.subplots(figsize=(6.6, 3.3))
    for (xs, ys), label, color, marker in (
        (capacity_profile, "vary capacity (numerator of rho)", ACCENT, "o"),
        (crew_profile, "vary crew size (denominator of rho)", VIOLET, "s"),
    ):
        x = np.asarray(list(xs), dtype=float)
        y = np.asarray(list(ys), dtype=float)
        order = np.argsort(x)
        ax.plot(x[order], y[order], marker=marker, markersize=4.5, linewidth=1.5,
                color=color, label=label)
    ax.axvline(1.0, color=MUTED, linewidth=0.9, linestyle=":")
    ax.set_ylim(-0.05, 1.08)
    _style(ax, xlabel=r"binding coverage $\rho_{min}$ (dimensionless)",
           ylabel="surviving crew fraction",
           title="Survival fraction versus coverage ratio from two independent sweeps")
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    return to_svg(fig)


__all__ = [
    "fig_archetypes",
    "fig_controllability",
    "fig_crew_scaling",
    "fig_criticality",
    "fig_loop_dynamics",
    "fig_mass_balance",
    "fig_pareto",
    "fig_phase_diagram",
    "fig_predictive_law",
    "fig_saturation",
    "fig_survival_curves",
    "to_svg",
]
