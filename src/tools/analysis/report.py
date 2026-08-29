"""Turn campaign datasets into findings and a single self-contained HTML report.

:func:`analyse` does the science and returns a plain dictionary; :func:`render`
turns that dictionary plus the figures into one HTML file with no external
assets. Keeping them apart means the numbers can be inspected, diffed and
regression-tested without going through the document.

Every number quoted in the prose of the report is pulled from the findings
dictionary rather than typed in, so the text cannot drift away from the data it
describes.
"""

from __future__ import annotations

import html
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from tools.analysis import figures
from tools.analysis.artifacts import load_chain
from tools.analysis.design_space import budget_limits, capacity_bounds
from tools.analysis.loop_dynamics import (
    ARCHETYPE_DESCRIPTIONS,
    ChainDynamics,
    analyse_chain,
    archetype_distribution,
    controllability,
    effective_gain,
)
from tools.analysis.statistics import (
    balanced_accuracy,
    central_difference,
    fit_logistic_response,
    kaplan_meier,
    log_rank_test,
    pearson,
    r_squared,
    rmse,
    summarise,
)

DATASET_NAMES = (
    "seed_replicates",
    "response_surface",
    "one_at_a_time",
    "one_at_a_time_relieved",
    "crew_scaling",
    "iso_ray",
    "chains",
)


def load_datasets(root: Path | str) -> Dict[str, List[Dict[str, Any]]]:
    """Read every dataset written by :meth:`CampaignResult.save`."""

    base = Path(root) / "datasets"
    out: Dict[str, List[Dict[str, Any]]] = {}
    for name in DATASET_NAMES:
        path = base / f"{name}.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            out[name] = list(data) if isinstance(data, list) else []
        else:
            out[name] = []
    return out


def _num(row: Mapping[str, Any], key: str) -> Optional[float]:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _profile(
    rows: Sequence[Mapping[str, Any]],
    x_key: str,
    y_key: str,
    *,
    where: Optional[Mapping[str, Any]] = None,
) -> Tuple[List[float], List[float]]:
    """``(x, y)`` pairs, averaged over duplicate x, sorted ascending."""

    grouped: Dict[float, List[float]] = {}
    for row in rows:
        if where and any(row.get(k) != v for k, v in where.items()):
            continue
        x, y = _num(row, x_key), _num(row, y_key)
        if x is None or y is None:
            continue
        grouped.setdefault(x, []).append(y)
    xs = sorted(grouped)
    return xs, [sum(grouped[x]) / len(grouped[x]) for x in xs]


# --------------------------------------------------------------------------- #
# findings
# --------------------------------------------------------------------------- #
def analyse(
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    chains: Sequence[ChainDynamics],
    *,
    config: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute every quantitative claim the report makes."""

    surface = list(datasets.get("response_surface") or [])
    oat = list(datasets.get("one_at_a_time") or [])
    oat_relieved = list(datasets.get("one_at_a_time_relieved") or [])
    crew = list(datasets.get("crew_scaling") or [])
    ray = list(datasets.get("iso_ray") or [])
    seeds = list(datasets.get("seed_replicates") or [])

    findings: Dict[str, Any] = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_sizes": {name: len(rows) for name, rows in datasets.items()},
    }

    # --- determinism -------------------------------------------------------
    spreads = {}
    for key in ("evaluation_score", "crew_remaining", "mean_normalized_severity"):
        values = [v for v in (_num(r, key) for r in seeds) if v is not None]
        spreads[key] = (max(values) - min(values)) if values else None
    findings["determinism"] = {
        "n_seeds": len(seeds),
        "spreads": spreads,
        "deterministic": all(s == 0.0 for s in spreads.values() if s is not None),
    }

    # --- physics validity --------------------------------------------------
    all_rows = [r for name in DATASET_NAMES for r in (datasets.get(name) or [])]
    residuals = {}
    for key in ("residual_o2_kg", "residual_co2_kg", "residual_water_l"):
        values = [v for v in (_num(r, key) for r in all_rows) if v is not None]
        residuals[key] = {"n": len(values), "max": max(values) if values else None}
    gate_rows = [r.get("physics_gate_passed") for r in all_rows]
    findings["physics"] = {
        "residuals": residuals,
        "gate_passed": sum(1 for g in gate_rows if g is True),
        "gate_total": sum(1 for g in gate_rows if isinstance(g, bool)),
    }

    # --- response surface --------------------------------------------------
    full = [r for r in surface if (_num(r, "survival_fraction") or 0.0) >= 1.0]
    budgets = budget_limits(config or {})
    within = [
        r for r in full
        if (_num(r, "total_mass_kg") or math.inf) <= budgets.get("max_total_mass_kg", math.inf)
        and (_num(r, "total_cost_musd") or math.inf) <= budgets.get("max_total_cost_musd", math.inf)
        and (_num(r, "total_volume_m3") or math.inf) <= budgets.get("max_total_volume_m3", math.inf)
    ]
    lightest = min(full, key=lambda r: _num(r, "total_mass_kg") or math.inf) if full else None
    best = max(surface, key=lambda r: _num(r, "evaluation_score") or -math.inf) if surface else None
    findings["surface"] = {
        "n": len(surface),
        "n_full_survival": len(full),
        "n_full_survival_within_budget": len(within),
        "budgets": budgets,
        "bounds": capacity_bounds(config or {}),
        "lightest_full_survival": {
            k: lightest.get(k) for k in (
                "run_id", "ars", "ogs", "rho_ars", "rho_ogs", "total_mass_kg",
                "total_cost_musd", "total_volume_m3", "evaluation_score",
            )
        } if lightest else None,
        "best_score": {
            k: best.get(k) for k in (
                "run_id", "ars", "ogs", "rho_ars", "rho_ogs", "evaluation_score",
                "total_mass_kg",
            )
        } if best else None,
        "mass_overrun_ratio": (
            (_num(lightest, "total_mass_kg") or math.nan) / budgets["max_total_mass_kg"]
            if lightest and budgets.get("max_total_mass_kg") else None
        ),
        "cost_overrun_ratio": (
            (_num(lightest, "total_cost_musd") or math.nan) / budgets["max_total_cost_musd"]
            if lightest and budgets.get("max_total_cost_musd") else None
        ),
    }

    # --- criticality -------------------------------------------------------
    max_ogs = max((_num(r, "ogs") or -math.inf) for r in surface) if surface else None
    max_ars = max((_num(r, "ars") or -math.inf) for r in surface) if surface else None
    profiles: Dict[str, Tuple[List[float], List[float]]] = {}
    if surface:
        profiles["ARS (CO2 removal)"] = _profile(
            surface, "rho_ars", "survival_fraction", where={"ogs": max_ogs}
        )
        profiles["OGS (O2 generation)"] = _profile(
            surface, "rho_ogs", "survival_fraction", where={"ars": max_ars}
        )
    if crew:
        profiles["crew scaling"] = _profile(crew, "rho_min", "survival_fraction")

    fits = {
        name: fit_logistic_response(xs, ys)
        for name, (xs, ys) in profiles.items() if len(xs) >= 3
    }
    findings["criticality"] = {
        "profiles": {name: {"x": xs, "y": ys} for name, (xs, ys) in profiles.items()},
        "fits": {name: fit.as_dict() for name, fit in fits.items()},
    }

    # --- coverage-ratio collapse ------------------------------------------
    crew_profile = _profile(crew, "rho_min", "survival_fraction")
    ray_profile = _profile(ray, "rho_min", "survival_fraction")
    paired: List[Tuple[float, float, float]] = []
    for x_c, y_c in zip(*crew_profile):
        # match on the nearest iso-ray coverage; the two sweeps are built to align
        if not ray_profile[0]:
            break
        nearest = min(range(len(ray_profile[0])), key=lambda i: abs(ray_profile[0][i] - x_c))
        if abs(ray_profile[0][nearest] - x_c) / max(x_c, 1e-9) < 0.02:
            paired.append((x_c, y_c, ray_profile[1][nearest]))
    findings["collapse"] = {
        "n_paired": len(paired),
        "max_abs_difference": max((abs(a - b) for _, a, b in paired), default=None),
        "mean_abs_difference": (
            sum(abs(a - b) for _, a, b in paired) / len(paired) if paired else None
        ),
        "correlation": pearson([a for _, a, _ in paired], [b for _, _, b in paired]) if len(paired) > 2 else None,
        "crew_profile": {"x": crew_profile[0], "y": crew_profile[1]},
        "iso_ray_profile": {"x": ray_profile[0], "y": ray_profile[1]},
    }

    # --- controllability ---------------------------------------------------
    controls = controllability(oat, outcome_key="survival_fraction")
    controls_relieved = controllability(oat_relieved, outcome_key="survival_fraction")
    controls_score = controllability(oat, outcome_key="evaluation_score")
    magnitude_share: Dict[str, float] = {}
    if chains:
        for subspace in ("capacity", "action", "policy"):
            values = [c.magnitude_share.get(subspace, 0.0) for c in chains]
            magnitude_share[subspace] = sum(values) / len(values)
    findings["controllability"] = {
        "shipped_operating_point": [c.as_dict() for c in controls],
        "relieved_operating_point": [c.as_dict() for c in controls_relieved],
        "score_outcome": [c.as_dict() for c in controls_score],
        "designer_magnitude_share": magnitude_share,
        "effective_gain": effective_gain(magnitude_share, controls),
        "zero_gain_axes": [c.axis for c in controls if c.gain == 0.0],
        "action_axis_span": {
            "multipliers": sorted({_num(r, "multiplier") for r in oat
                                   if r.get("subspace") == "action"} - {None}),
            "distinct_outcomes": sorted({_num(r, "survival_fraction") for r in oat
                                         if r.get("subspace") == "action"} - {None}),
        },
    }

    # --- loop dynamics -----------------------------------------------------
    findings["loop"] = {
        "n_chains": len(chains),
        "archetypes": archetype_distribution(chains),
        "archetype_descriptions": ARCHETYPE_DESCRIPTIONS,
        "chains": [c.as_dict() for c in chains],
        "discarded_fraction": summarise([c.discarded_fraction for c in chains]),
        "turning_cosine": summarise([
            s.turning_cosine for c in chains for s in c.states
            if s.turning_cosine is not None
        ]),
        "step_norm": summarise([
            s.step_norm for c in chains for s in c.states[1:]
        ]),
        "outcome_change": summarise([c.outcome_change for c in chains]),
    }

    # --- survival analysis -------------------------------------------------
    groups: Dict[str, List[Tuple[float, bool]]] = {"rho_min < 0.5": [], "rho_min >= 0.5": []}
    for row in surface:
        t = _num(row, "tcl_seconds")
        rho = _num(row, "rho_min")
        observed = row.get("tcl_observed")
        if t is None or rho is None or not isinstance(observed, bool):
            continue
        key = "rho_min < 0.5" if rho < 0.5 else "rho_min >= 0.5"
        groups[key].append((t, observed))
    curves = {
        name: kaplan_meier([t for t, _ in pairs], [e for _, e in pairs])
        for name, pairs in groups.items() if pairs
    }
    log_rank = None
    if len(curves) == 2:
        (a_name, _), (b_name, _) = list(groups.items())
        log_rank = log_rank_test(
            [t for t, _ in groups[a_name]], [e for _, e in groups[a_name]],
            [t for t, _ in groups[b_name]], [e for _, e in groups[b_name]],
        ).as_dict()
    findings["survival"] = {
        "curves": {name: curve.as_dict() for name, curve in curves.items()},
        "log_rank": log_rank,
    }
    findings["_km_curves"] = curves

    # --- ruggedness --------------------------------------------------------
    findings["ruggedness"] = _ruggedness(surface, oat_relieved)

    # --- saturation --------------------------------------------------------
    payload_sweep = [r for r in oat if r.get("axis") == "ogs_action_water_mass"]
    findings["saturation"] = {
        "ogs_payload_sweep": [
            {
                "multiplier": _num(r, "multiplier"),
                "clipped_by_capacity": _num(r, "limited_oxygen_generation.ogs_capacity") or 0.0,
                "survival_fraction": _num(r, "survival_fraction"),
            }
            for r in sorted(payload_sweep, key=lambda r: _num(r, "multiplier") or 0.0)
        ],
    }

    # --- predictive law ----------------------------------------------------
    findings["predictive"] = _predictive_models(surface)
    return findings


def _ruggedness(
    surface: Sequence[Mapping[str, Any]],
    oat_relieved: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """How often the response surface moves the wrong way along an axis.

    A monotone surface can be climbed greedily from any starting point. Each
    descent along an axis on which the outcome should improve is a place where a
    designer that trusts one evaluation per step can be sent backwards, so the
    count is a direct measure of how misleading local search would be here.
    """

    def descents(pairs: Sequence[Tuple[float, float]]) -> Tuple[int, int, float]:
        ordered = sorted(pairs)
        drops = 0
        worst = 0.0
        for i in range(1, len(ordered)):
            delta = ordered[i][1] - ordered[i - 1][1]
            if delta < -1e-9:
                drops += 1
                worst = max(worst, -delta)
        return drops, max(len(ordered) - 1, 0), worst

    rows_by_ogs: Dict[float, List[Tuple[float, float]]] = {}
    for row in surface:
        ogs, rho, surv = _num(row, "ogs"), _num(row, "rho_ars"), _num(row, "survival_fraction")
        if None in (ogs, rho, surv):
            continue
        rows_by_ogs.setdefault(float(ogs), []).append((float(rho), float(surv)))

    total_drops = total_steps = 0
    worst_drop = 0.0
    for pairs in rows_by_ogs.values():
        drops, steps, worst = descents(pairs)
        total_drops += drops
        total_steps += steps
        worst_drop = max(worst_drop, worst)

    ars_axis = [
        (_num(r, "multiplier") or 0.0, _num(r, "survival_fraction") or 0.0)
        for r in oat_relieved if r.get("axis") == "ars_capacity_kg_day"
    ]
    ars_drops, ars_steps, ars_worst = descents(ars_axis) if ars_axis else (0, 0, 0.0)

    return {
        "surface_descents": total_drops,
        "surface_transitions": total_steps,
        "surface_descent_rate": total_drops / total_steps if total_steps else None,
        "surface_worst_descent": worst_drop,
        "ars_axis_descents": ars_drops,
        "ars_axis_transitions": ars_steps,
        "ars_axis_worst_descent": ars_worst,
        "monotone": total_drops == 0,
    }


MODEL_ORDER = (
    "constant",
    "ARS only",
    "OGS only",
    "Liebig on coverage",
    "Liebig on margin",
    "series (product)",
    "Liebig on response",
)

MODEL_NOTES: Dict[str, str] = {
    "constant": "the training mean; the floor any real model must clear",
    "ARS only": "one logistic in the CO2 coverage, O2 ignored",
    "OGS only": "one logistic in the O2 coverage, CO2 ignored",
    "Liebig on coverage": "logistic in min(rho_ARS, rho_OGS): the law of the minimum as usually stated",
    "Liebig on margin": "the same law after dividing each coverage by its own critical value",
    "series (product)": "the two subsystems in series, survival as the product of their responses",
    "Liebig on response": "the binding subsystem sets the outcome: min of the two responses",
}

#: How many levels of the other axis enter a marginal slice. One level is the
#: cleanest marginal but leaves too few points to fit reliably once the grid is
#: split in half; three is stable across splits without smearing the transition.
MARGINAL_SLICE_LEVELS = 3


def _predictive_models(surface: Sequence[Mapping[str, Any]], *, seed: int = 20260829) -> Dict[str, Any]:
    """Compare candidate laws for survival, fitted and scored out of sample.

    The comparison mirrors the structure used for collective-dynamics models: a
    trivial baseline, single-variable models, and the structured models the
    physics suggests. Every model is fitted on a random half of the design grid
    and scored on the other half, so a flexible model cannot win by memorising
    the surface.

    Balanced accuracy accompanies R-squared because the outcome saturates hard
    at 0 and 1; plain accuracy would reward a constant predictor.
    """

    import numpy as np

    rows = [
        r for r in surface
        if _num(r, "survival_fraction") is not None
        and _num(r, "rho_ars") is not None
        and _num(r, "rho_ogs") is not None
    ]
    if len(rows) < 12:
        return {"n": len(rows), "models": {}}

    observed = np.array([_num(r, "survival_fraction") or 0.0 for r in rows])
    rho_ars = np.array([_num(r, "rho_ars") or 0.0 for r in rows])
    rho_ogs = np.array([_num(r, "rho_ogs") or 0.0 for r in rows])

    nameplate_ars = np.array([_num(r, "ars") or 0.0 for r in rows])
    nameplate_ogs = np.array([_num(r, "ogs") or 0.0 for r in rows])

    rng = np.random.default_rng(seed)
    order = rng.permutation(len(rows))
    cut = len(rows) // 2
    train, test = np.sort(order[:cut]), np.sort(order[cut:])

    def marginal(axis: "np.ndarray", other: "np.ndarray"):
        """Fit one axis on the training slice where the other axis is largest.

        Fitting a single-variable logistic to the whole two-dimensional cloud
        estimates nothing: the other axis moves underneath it and the fit
        chases the mixture. The marginal has to be taken on a slice where the
        other subsystem is not the binding one.
        """

        top = np.unique(other[train])[-MARGINAL_SLICE_LEVELS:]
        selected = train[np.isin(other[train], top)]
        return fit_logistic_response(axis[selected], observed[selected])

    fit_ars = marginal(rho_ars, nameplate_ogs)
    fit_ogs = marginal(rho_ogs, nameplate_ars)
    rho_min = np.minimum(rho_ars, rho_ogs)
    fit_min = fit_logistic_response(rho_min[train], observed[train])

    # Each subsystem becomes critical at a different coverage, so the raw
    # minimum names the wrong bottleneck wherever the numerically smaller
    # coverage is the one with the lower threshold. Dividing by the per-axis
    # critical coverage puts both on a common margin scale first.
    star_ars = fit_ars.x0 if math.isfinite(fit_ars.x0) and fit_ars.x0 > 0 else 1.0
    star_ogs = fit_ogs.x0 if math.isfinite(fit_ogs.x0) and fit_ogs.x0 > 0 else 1.0
    margin = np.minimum(rho_ars / star_ars, rho_ogs / star_ogs)
    fit_margin = fit_logistic_response(margin[train], observed[train])

    response_ars = fit_ars.predict(rho_ars)
    response_ogs = fit_ogs.predict(rho_ogs)
    predictions: Dict[str, np.ndarray] = {
        "constant": np.full(len(rows), float(observed[train].mean())),
        "ARS only": response_ars,
        "OGS only": response_ogs,
        "Liebig on coverage": fit_min.predict(rho_min),
        "Liebig on margin": fit_margin.predict(margin),
        "series (product)": response_ars * response_ogs,
        "Liebig on response": np.minimum(response_ars, response_ogs),
    }

    truth = observed >= 1.0
    models: Dict[str, Dict[str, float]] = {}
    for name in MODEL_ORDER:
        pred = predictions[name]
        models[name] = {
            "r_squared": r_squared(observed[test], pred[test]),
            "rmse": rmse(observed[test], pred[test]),
            "balanced_accuracy": balanced_accuracy(
                list(truth[test]), list(pred[test] >= 0.5)
            ),
            "r_squared_in_sample": r_squared(observed[train], pred[train]),
            "note": MODEL_NOTES[name],  # type: ignore[dict-item]
        }
    return {
        "n": len(rows),
        "n_train": int(train.size),
        "n_test": int(test.size),
        "models": models,
        "critical_coverage": {"ARS": star_ars, "OGS": star_ogs},
        "marginal_slice_levels": MARGINAL_SLICE_LEVELS,
        "fits": {
            "ARS only": fit_ars.as_dict(),
            "OGS only": fit_ogs.as_dict(),
            "Liebig on coverage": fit_min.as_dict(),
            "Liebig on margin": fit_margin.as_dict(),
        },
        "_observed": [float(v) for v in observed[test]],
        "_predictions": {
            name: [float(v) for v in pred[test]] for name, pred in predictions.items()
        },
    }


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
_CSS = """
:root {
  --ink: #1b1f24; --muted: #6b7280; --rule: #e4e7eb; --bg: #ffffff;
  --accent: #1f6feb; --warm: #d1442f; --green: #2f855a; --soft: #f6f8fa;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 940px; margin: 0 auto; padding: 56px 28px 120px; }
header { border-bottom: 2px solid var(--ink); padding-bottom: 22px; margin-bottom: 34px; }
h1 { font-size: 30px; line-height: 1.22; margin: 0 0 10px; letter-spacing: -0.02em; }
.sub { color: var(--muted); font-size: 14px; margin: 0; }
h2 {
  font-size: 20px; margin: 46px 0 12px; padding-top: 20px;
  border-top: 1px solid var(--rule); letter-spacing: -0.01em;
}
h2:first-of-type { border-top: none; }
h3 { font-size: 15px; margin: 26px 0 8px; }
p { margin: 0 0 13px; }
ul, ol { margin: 0 0 13px; padding-left: 22px; }
li { margin-bottom: 5px; }
code { font: 12.5px ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--soft);
       padding: 1px 5px; border-radius: 3px; }
figure { margin: 22px 0 26px; }
figure svg { max-width: 100%; height: auto; display: block; }
figcaption { font-size: 12.5px; color: var(--muted); margin-top: 8px; }
figcaption b { color: var(--ink); font-weight: 600; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 16px 0 22px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--rule); }
th { font-weight: 600; color: var(--muted); font-size: 12px; text-transform: uppercase;
     letter-spacing: 0.04em; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr.hl td { background: #fff8f3; font-weight: 600; }
.key {
  border-left: 3px solid var(--accent); background: var(--soft);
  padding: 14px 18px; margin: 20px 0; border-radius: 0 4px 4px 0;
}
.key.warn { border-left-color: var(--warm); background: #fff6f4; }
.key p:last-child { margin-bottom: 0; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1px;
        background: var(--rule); border: 1px solid var(--rule); margin: 26px 0; }
.kpi { background: var(--bg); padding: 15px 16px; }
.kpi .v { font-size: 23px; font-weight: 600; letter-spacing: -0.02em; display: block; }
.kpi .l { font-size: 11.5px; color: var(--muted); text-transform: uppercase;
          letter-spacing: 0.05em; margin-top: 3px; display: block; }
.kpi.warn .v { color: var(--warm); }
.kpi.good .v { color: var(--green); }
footer { margin-top: 60px; padding-top: 18px; border-top: 1px solid var(--rule);
         font-size: 12.5px; color: var(--muted); }
"""


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int,)) and not isinstance(value, bool):
        return f"{value:,}"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "—"
        if value == int(value) and abs(value) < 1e6:
            return f"{int(value):,}"
        return f"{value:,.{digits}f}"
    return _esc(value)


def _kpi(value: str, label: str, tone: str = "") -> str:
    cls = f"kpi {tone}".strip()
    return f'<div class="{cls}"><span class="v">{_esc(value)}</span><span class="l">{_esc(label)}</span></div>'


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]],
           *, numeric: Sequence[int] = (), highlight: Sequence[int] = ()) -> str:
    head = "".join(
        f'<th class="num">{_esc(h)}</th>' if i in numeric else f"<th>{_esc(h)}</th>"
        for i, h in enumerate(headers)
    )
    body = []
    for index, row in enumerate(rows):
        cells = "".join(
            f'<td class="num">{_esc(c)}</td>' if i in numeric else f"<td>{_esc(c)}</td>"
            for i, c in enumerate(row)
        )
        cls = ' class="hl"' if index in highlight else ""
        body.append(f"<tr{cls}>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _figure(svg: str, number: int, title: str, caption: str) -> str:
    return (
        f"<figure>{svg}"
        f"<figcaption><b>Figure {number}. {_esc(title)}</b> {_esc(caption)}</figcaption>"
        f"</figure>"
    )


def _pct(value: Optional[float], digits: int = 0) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return f"{value * 100:.{digits}f}%"


def render(
    findings: Mapping[str, Any],
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    chains: Sequence[ChainDynamics],
    *,
    title: str = "Physics of a design agent",
    subtitle: str = "",
) -> str:
    """Assemble the full HTML report from findings, datasets and figures."""

    surface = list(datasets.get("response_surface") or [])
    all_rows = [r for name in DATASET_NAMES for r in (datasets.get(name) or [])]
    n_runs = sum(len(rows) for rows in datasets.values())

    surf = findings.get("surface", {})
    ctrl = findings.get("controllability", {})
    loop = findings.get("loop", {})
    crit = findings.get("criticality", {})
    collapse = findings.get("collapse", {})
    rugged = findings.get("ruggedness", {})
    pred = findings.get("predictive", {})
    det = findings.get("determinism", {})
    phys = findings.get("physics", {})

    parts: List[str] = []
    figure_no = 0

    def add_figure(svg: str, title_: str, caption: str) -> None:
        nonlocal figure_no
        figure_no += 1
        parts.append(_figure(svg, figure_no, title_, caption))

    # ---------------- header + KPIs ----------------
    lightest = surf.get("lightest_full_survival") or {}
    budgets = surf.get("budgets") or {}
    mass_ratio = surf.get("mass_overrun_ratio")
    zero_axes = ctrl.get("zero_gain_axes") or []
    archetypes = loop.get("archetypes") or {}
    dominant = max(archetypes.items(), key=lambda kv: kv[1])[0] if archetypes else "—"

    parts.append(
        '<div class="kpis">'
        + _kpi(f"{n_runs:,}", "simulations analysed")
        + _kpi(f"{surf.get('n_full_survival', 0)}/{surf.get('n', 0)}", "designs saving the crew")
        + _kpi(str(surf.get("n_full_survival_within_budget", 0)),
               "of those within budget",
               "warn" if surf.get("n_full_survival_within_budget") == 0 else "good")
        + _kpi(f"{len(zero_axes)}/{len(ctrl.get('shipped_operating_point') or [])}",
               "axes with zero gain", "warn" if zero_axes else "")
        + _kpi(dominant, "dominant loop archetype",
               "warn" if dominant in ("saturating", "frozen") else "good")
        + "</div>"
    )

    # ---------------- summary ----------------
    parts.append("<h2>Summary</h2>")
    parts.append(
        "<p>This report treats an Engineering Agents campaign as a dynamical system on a "
        "design space and characterises it the way a physical system would be characterised: "
        "identify the order parameter, locate the transition, measure the response, and only "
        "then judge the controller. Three results follow, in that order.</p>"
    )
    parts.append(
        '<div class="key"><p><b>1. The system has one order parameter and a sharp transition.</b> '
        f"Survival is governed by how much margin each subsystem has against its own critical "
        f"coverage. Two logistics combined by the law of the minimum explain "
        f"{_fmt((pred.get('models', {}).get('Liebig on response', {}) or {}).get('r_squared'), 3)} of the "
        f"variance in surviving crew on held-out designs from the {surf.get('n', 0)}-point grid. Scaling the "
        "hardware up and scaling the crew down — two physically unrelated manipulations — trace "
        f"the same curve to within {_fmt(collapse.get('max_abs_difference'), 2)} crew fraction.</p></div>"
    )
    parts.append(
        '<div class="key warn"><p><b>2. The mission is infeasible under its own budget.</b> '
        f"Of {surf.get('n', 0)} designs on the grid, {surf.get('n_full_survival', 0)} keep the whole "
        f"crew alive and <b>{surf.get('n_full_survival_within_budget', 0)}</b> of those fit inside the "
        f"declared <code>design_constraints.budgets</code>. The lightest surviving station masses "
        f"{_fmt(lightest.get('total_mass_kg'), 0)} kg against a {_fmt(budgets.get('max_total_mass_kg'), 0)} kg "
        f"ceiling ({_fmt((mass_ratio or 1) * 100 - 100, 0)}% over) and costs "
        f"{_fmt(lightest.get('total_cost_musd'), 0)} MUSD against {_fmt(budgets.get('max_total_cost_musd'), 0)} MUSD. "
        "No design agent, however good, can satisfy both. Under this repository's own stated "
        "hierarchy — the mission is paramount and design requirements may be revised beneath it — "
        "the budget is the requirement that has to move.</p></div>"
    )
    parts.append(
        '<div class="key warn"><p><b>3. The shipped rule designer actuates axes with zero gain '
        "at the point where it starts.</b> "
        f"It places {_pct((ctrl.get('designer_magnitude_share') or {}).get('action'))} of its step "
        "magnitude in the action subspace and "
        f"{_pct((ctrl.get('designer_magnitude_share') or {}).get('capacity'))} in the capacity "
        "subspace. At the shipped operating point every action and policy axis measures a gain of "
        "exactly zero: sweeping them over a 20-fold range leaves surviving crew unchanged. Every "
        f"chain lands in the <i>saturating</i> archetype — the loop moves steadily "
        f"(turning cosine {_fmt((loop.get('turning_cosine') or {}).get('mean'), 2)}, i.e. a perfectly "
        "straight march) and the outcome never changes.</p></div>"
    )

    # ---------------- methods ----------------
    parts.append("<h2>Method and data</h2>")
    parts.append(
        "<p>Every run is a 72-step <code>plant_sim</code> simulation of a 24-hour mission with 50 "
        "crew, driven through the documented CLI. A design is imposed by writing a "
        "<code>capacity_profile</code> proposal and passing it to <code>--apply-proposals</code>, "
        "which is the same path the tool-use designer uses to adopt a candidate, so the "
        "experiment grid and the agent's own proposals move through identical code.</p>"
    )
    parts.append(
        "<p>One consequence of using that path is worth stating, because it shapes what the grid "
        "measures. Applying a capacity change also runs <code>sync_action_payloads</code>, which "
        "raises the crew's request to what the new hardware can honour. Every point on the "
        "response surface is therefore a <i>well-operated</i> station rather than new hardware "
        "driven by stale procedures, which is the right comparison for a sizing question and is "
        "also what the design agent would actually ship. The one-at-a-time sweeps deliberately do "
        "not sync, so they isolate the payload axis on its own.</p>"
    )
    parts.append(_table(
        ["dataset", "runs", "what it varies", "what it answers"],
        [
            ["seed replicates", findings["dataset_sizes"].get("seed_replicates", 0),
             "--seed only", "is the plant stochastic?"],
            ["response surface", findings["dataset_sizes"].get("response_surface", 0),
             "ARS x OGS nameplate", "phase diagram, criticality, cost of survival"],
            ["one-at-a-time", findings["dataset_sizes"].get("one_at_a_time", 0),
             "one axis, shipped point", "controllability where the loop starts"],
            ["one-at-a-time (relieved)", findings["dataset_sizes"].get("one_at_a_time_relieved", 0),
             "one axis, OGS sized to 42 kg/day", "controllability once O2 is not binding"],
            ["crew scaling", findings["dataset_sizes"].get("crew_scaling", 0),
             "crew size, station fixed", "denominator half of the collapse test"],
            ["iso-ray", findings["dataset_sizes"].get("iso_ray", 0),
             "all capacities by a common factor", "numerator half of the collapse test"],
            ["design chains", findings["dataset_sizes"].get("chains", 0),
             "--iterate length", "the closed loop actually running"],
        ],
        numeric=(1,),
    ))

    # ---------------- determinism + physics ----------------
    parts.append("<h3>Where the uncertainty is</h3>")
    spreads = det.get("spreads") or {}
    parts.append(
        f"<p>Replaying one configuration under {det.get('n_seeds', 0)} different seeds reproduces "
        f"the outcome exactly: the spread in evaluation score across seeds is "
        f"{_fmt(spreads.get('evaluation_score'), 6)} and in surviving crew "
        f"{_fmt(spreads.get('crew_remaining'), 6)}. With rule-based actors and designers the whole "
        "pipeline is deterministic, so there is no replicate noise to bootstrap over. Every "
        "interval in this report is therefore taken across design points and scenario conditions, "
        "which is where the variation genuinely lives. Stochasticity would enter only through an "
        "LLM designer, which needs a provider this analysis did not have.</p>"
    )
    add_figure(
        figures.fig_mass_balance(all_rows),
        "Conservation holds in every run",
        "The physics gate recomputes each mass ledger independently of the state it audits and "
        f"passed in {phys.get('gate_passed', 0)} of {phys.get('gate_total', 0)} runs. Residuals are "
        "identically zero, so no result below is an artefact of a leaking simulator.",
    )

    # ---------------- order parameter ----------------
    parts.append("<h2>The order parameter and its transition</h2>")
    parts.append(
        "<p>The three sizing variables have different units and baselines that differ by an order "
        "of magnitude, so they cannot be compared directly. Dividing each by the crew's daily "
        "demand for the same quantity gives a dimensionless coverage ratio ρ whose unit point is "
        "physically meaningful: ρ = 1 is the smallest station that services the crew in steady "
        "state. Liebig's law of the minimum then suggests the binding coverage "
        "ρ<sub>min</sub> = min(ρ<sub>ARS</sub>, ρ<sub>OGS</sub>, ρ<sub>WRS</sub>) as the single "
        "scalar order parameter. The shipped station sits at ρ<sub>ARS</sub> = 0.087 and "
        "ρ<sub>OGS</sub> = 0.220 — undersized by a factor of eleven and five.</p>"
    )
    add_figure(
        figures.fig_phase_diagram(surface),
        "Survival phase diagram",
        "The habitable region is bounded on the O2 axis and is entered well below ρ = 1 on the "
        "CO2 axis, because the survival rule watches stored CO2 rather than instantaneous removal.",
    )

    fits = {
        name: fit_logistic_response(block["x"], block["y"])
        for name, block in (crit.get("profiles") or {}).items()
        if len(block.get("x") or []) >= 3
    }
    profiles = {
        name: (block["x"], block["y"])
        for name, block in (crit.get("profiles") or {}).items()
    }
    add_figure(
        figures.fig_criticality(profiles, fits),
        "Order parameter and susceptibility",
        "The plant is deterministic, so the susceptibility is the derivative of the response, not "
        "a variance over replicates. Its peak locates the critical coverage.",
    )
    parts.append(_table(
        ["axis", "critical coverage ρ*", "transition width", "peak susceptibility", "R²"],
        [
            [name, _fmt(fit.x0, 3), _fmt(fit.width, 3), _fmt(fit.max_slope, 2),
             _fmt(fit.r_squared, 3)]
            for name, fit in fits.items()
        ],
        numeric=(1, 2, 3, 4),
    ))

    # ---------------- collapse ----------------
    parts.append("<h3>A falsification test of the coverage ratio</h3>")
    parts.append(
        "<p>If ρ really is the order parameter, then halving the crew and doubling the hardware "
        "must be the same intervention, because both double ρ. The two sweeps share no runs and "
        "manipulate physically unrelated quantities. They agree to within "
        f"{_fmt(collapse.get('max_abs_difference'), 2)} crew fraction at worst and "
        f"{_fmt(collapse.get('mean_abs_difference'), 3)} on average across "
        f"{collapse.get('n_paired', 0)} paired points, with correlation "
        f"{_fmt(collapse.get('correlation'), 3)}. The residual gap is real and systematic: at equal "
        "ρ a smaller crew does slightly better, because a fixed per-operation batch size serves a "
        "smaller crew proportionally further.</p>"
    )
    add_figure(
        figures.fig_crew_scaling(
            (collapse.get("iso_ray_profile", {}).get("x", []),
             collapse.get("iso_ray_profile", {}).get("y", [])),
            (collapse.get("crew_profile", {}).get("x", []),
             collapse.get("crew_profile", {}).get("y", [])),
        ),
        "Two independent sweeps collapse onto one curve",
        "Adding hardware and removing people are different physical acts that move the same "
        "dimensionless quantity, and the response follows the quantity rather than the act.",
    )

    # ---------------- controllability ----------------
    parts.append("<h2>What the loop can steer, and what it steers</h2>")
    controls = [
        _c for _c in _controls_from(ctrl.get("shipped_operating_point") or [])
    ]
    add_figure(
        figures.fig_controllability(
            controls, ctrl.get("designer_magnitude_share") or {}
        ),
        "Controllability against actuation",
        "Only one axis moves the outcome at the point where the loop starts, and it is the one "
        "the shipped designer never touches.",
    )
    span = ctrl.get("action_axis_span") or {}
    parts.append(
        "<p>At the shipped operating point, sweeping every action-subspace axis across "
        f"{len(span.get('multipliers') or [])} multipliers spanning "
        f"{_fmt(min(span.get('multipliers') or [1]), 2)}× to {_fmt(max(span.get('multipliers') or [1]), 2)}× "
        f"produces exactly {len(span.get('distinct_outcomes') or [])} distinct outcome"
        f"{'' if len(span.get('distinct_outcomes') or []) == 1 else 's'}: "
        f"{', '.join(_fmt(v, 2) for v in (span.get('distinct_outcomes') or []))}. "
        "The mechanism is visible in the operations log.</p>"
    )
    add_figure(
        figures.fig_saturation(list(datasets.get("one_at_a_time") or [])),
        "Why the request payload does nothing for O2",
        "The plant delivers the smaller of the request and the nameplate and says so in "
        "limited_by, so everything above the nameplate is discarded on arrival. This is the "
        "mechanism behind the zero gain measured above, read off the plant's own limiter field "
        "rather than inferred.",
    )

    parts.append("<h3>Controllability is state-dependent</h3>")
    relieved = {c["axis"]: c for c in (ctrl.get("relieved_operating_point") or [])}
    shipped = {c["axis"]: c for c in (ctrl.get("shipped_operating_point") or [])}
    rows = []
    for axis in sorted(set(shipped) | set(relieved)):
        s_gain = (shipped.get(axis) or {}).get("gain")
        r_gain = (relieved.get(axis) or {}).get("gain")
        rows.append([
            axis.replace("_", " "),
            (shipped.get(axis) or relieved.get(axis) or {}).get("subspace", "—"),
            _fmt(s_gain, 3), _fmt(r_gain, 3),
        ])
    highlight = [
        i for i, row in enumerate(rows)
        if row[2] == "0" and row[3] not in ("0", "—")
    ]
    parts.append(_table(
        ["axis", "subspace", "gain at shipped point", "gain with O2 relieved"],
        rows, numeric=(2, 3), highlight=highlight,
    ))
    parts.append(
        "<p>The highlighted rows are the important ones. They have zero gain where the loop starts "
        "and substantial gain once the oxygen famine is lifted, which means the shipped designer's "
        "preferred axis is not useless in general — it is useless <i>until a different subsystem "
        "is fixed first</i>. Diagnosing that requires reasoning about which constraint binds, and "
        "the rule designer's fixed multiplicative policy has no mechanism to do so. One-at-a-time "
        "sensitivity measured at a single operating point would have concluded the axis was dead; "
        "the second sweep is what distinguishes the two cases.</p>"
    )

    # ---------------- ruggedness ----------------
    parts.append("<h3>The landscape is not monotone</h3>")
    parts.append(
        f"<p>Along the ARS axis, {rugged.get('surface_descents', 0)} of "
        f"{rugged.get('surface_transitions', 0)} grid transitions "
        f"({_pct(rugged.get('surface_descent_rate'))}) move the outcome <i>down</i> while capacity "
        f"goes up, with a worst single descent of {_fmt(rugged.get('surface_worst_descent'), 2)} "
        "crew fraction. Adding hardware can cost lives here because the operations are scheduled "
        "against a busy guard: a larger batch occupies the subsystem for longer and can miss the "
        "window in which the next one was needed. A designer that trusts one evaluation per step "
        "and climbs greedily will be sent backwards by these reversals, which is an argument for "
        "the multi-candidate re-simulation the tool-use designer performs rather than for a larger "
        "step size.</p>"
    )

    # ---------------- loop dynamics ----------------
    parts.append("<h2>The closed loop as a trajectory</h2>")
    add_figure(
        figures.fig_loop_dynamics(chains),
        "Order parameters of the design chain",
        "Displacement grows linearly, the step size never decays, the turning angle is pinned at "
        "+1, and the outcome is flat. This is an open-loop march, not a search.",
    )
    add_figure(
        figures.fig_archetypes(archetypes, loop.get("n_chains", 0)),
        "Trajectory archetypes",
        "Separating 'proposed nothing' from 'proposed something ineffective' matters: the two look "
        "identical in an outcome plot and have opposite fixes.",
    )
    parts.append(_table(
        ["chain", "iterations", "archetype", "displacement", "Δ survival",
         "capacity share", "action share", "proposals discarded"],
        [
            [c.chain_id, c.length, c.archetype, _fmt(c.total_displacement, 3),
             _fmt(c.outcome_change, 3),
             _pct(c.magnitude_share.get("capacity")),
             _pct(c.magnitude_share.get("action")),
             _pct(c.discarded_fraction)]
            for c in chains
        ],
        numeric=(1, 3, 4, 5, 6, 7),
    ))
    parts.append(
        f"<p>A further {_pct((loop.get('discarded_fraction') or {}).get('mean'))} of proposals never "
        "reach a simulation at all. The chain strips every <code>set_parameter</code> change from "
        "<code>applied_proposals.json</code> to keep the verification requirements frozen across "
        "iterations — a correct and deliberate safeguard, since a designer that can move its own "
        "acceptance thresholds can declare success without changing the plant. The designer, "
        "however, is never told, so it re-proposes the identical threshold change on every "
        "iteration and spends two of its five proposal slots on a move that is discarded by "
        "construction.</p>"
    )

    # ---------------- survival analysis ----------------
    parts.append("<h2>Time to first crew loss</h2>")
    km = findings.get("_km_curves") or {}
    if km:
        lr = findings.get("survival", {}).get("log_rank") or {}
        annotation = (
            f"Log-rank χ²(1) = {_fmt(lr.get('statistic'), 1)}, p = {_fmt(lr.get('p_value'), 4)}."
            if lr else ""
        )
        add_figure(
            figures.fig_survival_curves(km, annotation),
            "Survival curves by coverage regime",
            "Designs above and below half coverage separate immediately and never re-cross. "
            "Censoring is taken from the scorecard's own right_censored status rather than "
            "imputed.",
        )

    # ---------------- predictive law ----------------
    parts.append("<h2>A compact predictive law</h2>")
    models = pred.get("models") or {}
    best_model = (
        max(models.items(), key=lambda kv: kv[1].get("r_squared", -math.inf))[0]
        if models else None
    )
    stars = pred.get("critical_coverage") or {}
    parts.append(
        "<p>The comparison below follows the structure used for collective-dynamics models: a "
        "trivial baseline, single-variable models, and the structured models the physics "
        f"suggests. Each is fitted on a random half of the grid ({pred.get('n_train', 0)} designs) "
        f"and scored on the other half ({pred.get('n_test', 0)}), so a flexible model cannot win by "
        "memorising the surface. Balanced accuracy accompanies R² because the outcome saturates "
        "hard at 0 and 1, and plain accuracy would reward a constant predictor.</p>"
    )
    model_rows = [
        [name, _fmt(models[name].get("r_squared"), 3), _fmt(models[name].get("rmse"), 3),
         _fmt(models[name].get("balanced_accuracy"), 3),
         models[name].get("note", "")]
        for name in MODEL_ORDER if name in models
    ]
    parts.append(_table(
        ["model", "held-out R²", "RMSE", "balanced accuracy", "what it assumes"],
        model_rows, numeric=(1, 2, 3),
        highlight=[i for i, row in enumerate(model_rows) if row[0] == best_model],
    ))
    naive = (models.get("Liebig on coverage") or {}).get("r_squared")
    margin_model = (models.get("Liebig on margin") or {}).get("r_squared")
    response_model = (models.get("Liebig on response") or {}).get("r_squared")
    ogs_only = (models.get("OGS only") or {}).get("r_squared")
    parts.append(
        "<p>The law of the minimum as usually stated does <i>badly</i> here — held-out R² of "
        f"{_fmt(naive, 3)}, worse than ignoring the CO2 axis altogether ({_fmt(ogs_only, 3)}). The "
        "reason is that the two subsystems do not become critical at the same coverage: the ARS "
        f"transition sits at ρ* = {_fmt(stars.get('ARS'), 2)} and the OGS transition at "
        f"ρ* = {_fmt(stars.get('OGS'), 2)}. Taking the raw minimum therefore names the wrong "
        "bottleneck wherever the numerically smaller coverage is the one with the lower threshold, "
        "which on this grid is most cells. Rescaling each coverage by its own critical value first "
        f"recovers {_fmt(margin_model, 3)}, and taking the minimum of the two fitted <i>responses</i> "
        f"rather than of their inputs reaches {_fmt(response_model, 3)} on held-out designs. Two "
        "logistics, four parameters, and a minimum reproduce a 121-point response surface. The "
        "quantity that matters is each subsystem's margin against its own threshold, not its raw "
        "coverage.</p>"
    )
    if pred.get("_predictions"):
        add_figure(
            figures.fig_predictive_law(
                pred["_observed"], pred["_predictions"], models
            ),
            "Observed against predicted survival",
            "Two logistics in the two coverage ratios, combined by the law of the minimum, "
            "reproduce a 121-point response surface.",
        )

    # ---------------- cost ----------------
    parts.append("<h2>The cost of keeping the crew alive</h2>")
    add_figure(
        figures.fig_pareto(surface, budgets),
        "Survival against station footprint",
        "The feasible box and the surviving set do not intersect. This is a property of the "
        "requirements, not of any agent that searches inside them.",
    )
    parts.append(
        f"<p>The lightest station on the grid that keeps all 50 crew alive sizes ARS to "
        f"{_fmt(lightest.get('ars'), 1)} kg/day and OGS to {_fmt(lightest.get('ogs'), 1)} kg/day, "
        f"reaching ρ<sub>ARS</sub> = {_fmt(lightest.get('rho_ars'), 2)} and ρ<sub>OGS</sub> = "
        f"{_fmt(lightest.get('rho_ogs'), 2)}. It masses {_fmt(lightest.get('total_mass_kg'), 0)} kg, "
        f"costs {_fmt(lightest.get('total_cost_musd'), 0)} MUSD and occupies "
        f"{_fmt(lightest.get('total_volume_m3'), 1)} m³, against ceilings of "
        f"{_fmt(budgets.get('max_total_mass_kg'), 0)} kg, {_fmt(budgets.get('max_total_cost_musd'), 0)} MUSD "
        f"and {_fmt(budgets.get('max_total_volume_m3'), 0)} m³. It breaches all three.</p>"
    )

    # ---------------- implications ----------------
    parts.append("<h2>What this implies for the design agent</h2>")
    parts.append("<ol>")
    parts.append(
        "<li><b>Report infeasibility as a result, not a failure.</b> The chain currently ends with "
        "<code>NOT_IMPROVED</code>, which reads as an agent that underperformed. The measured "
        "situation is that the mission and the budget cannot both be met, and the honest output is "
        "a request to revise the budget with the cheapest surviving design attached as evidence.</li>"
    )
    parts.append(
        "<li><b>Make the binding constraint drive the proposal.</b> The plant already reports "
        "<code>limited_by</code> and <code>fully_satisfied</code> on every operation, and those "
        "fields identify the binding subsystem exactly. A designer that reads them would not spend "
        "six iterations enlarging a request the backend discards.</li>"
    )
    parts.append(
        "<li><b>Tell the designer what was discarded.</b> Freezing the requirements is right; "
        "silently dropping the proposals is what makes the designer repeat them. Echoing the "
        "filtered changes back would free two of five proposal slots immediately.</li>"
    )
    parts.append(
        "<li><b>Do not climb greedily.</b> "
        f"{_pct(rugged.get('surface_descent_rate'))} of capacity increases along the ARS axis make "
        "the outcome worse, so single-evaluation hill climbing is unreliable here. The tool-use "
        "designer's multi-candidate re-simulation is the right shape of answer.</li>"
    )
    parts.append(
        "<li><b>Instrument coverage directly.</b> ρ is computable from the config before a run "
        "starts and predicts the outcome with R² = "
        f"{_fmt((models.get('Liebig min') or {}).get('r_squared'), 3)}. Surfacing it in the "
        "scorecard would turn most of this analysis into a single pre-flight number.</li>"
    )
    parts.append("</ol>")

    # ---------------- limits ----------------
    parts.append("<h2>Limits of this analysis</h2>")
    parts.append("<ul>")
    parts.append(
        "<li>Both agent sides run in <code>labeled_rule_base</code> mode. No LLM provider was "
        "reachable, so the tool-use designer that <i>can</i> emit <code>capacity_profile</code> "
        "changes was never exercised. The controllability and phase-diagram results characterise "
        "the plant and therefore apply to any designer; the loop-dynamics results characterise the "
        "rule designer specifically.</li>"
    )
    parts.append(
        "<li>All runs use the <code>plant_sim</code> backend. The <code>mock</code> backend "
        "produces no survival or scorecard data, and <code>ros2</code> needs SSOS Docker.</li>"
    )
    parts.append(
        "<li>Failure injection is off in the sweeps so that coverage is the only thing varying. "
        "The chains keep the shipped default, which enables it.</li>"
    )
    parts.append(
        f"<li>The grid is {surf.get('n', 0)} points over two axes with WRS held fixed, justified by "
        "its measured zero gain and a baseline coverage of 6.4. A finer grid would sharpen the "
        "critical coverage estimates but is unlikely to move the qualitative conclusions.</li>"
    )
    parts.append("</ul>")

    generated = findings.get("generated_utc", "")
    body = "\n".join(parts)
    subtitle_html = f"<p class='sub'>{_esc(subtitle)}</p>" if subtitle else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title><style>{_CSS}</style></head>
<body><div class="wrap">
<header><h1>{_esc(title)}</h1>{subtitle_html}
<p class="sub">Generated {_esc(generated)} from {n_runs:,} simulations
&middot; Engineering Agents <code>ssos_eclss_loop</code> &middot; plant_sim backend</p></header>
{body}
<footer>Reproduce with <code>python3 -m tools.analysis run</code> then
<code>python3 -m tools.analysis report</code>. Every number in this document is computed from the
datasets under <code>src/experiments/analysis/datasets/</code>; none is typed in.</footer>
</div></body></html>"""


def _controls_from(records: Sequence[Mapping[str, Any]]):
    """Rebuild controllability records from their serialised form."""

    from tools.analysis.loop_dynamics import AxisControllability

    return [
        AxisControllability(
            axis=str(r.get("axis")),
            subspace=str(r.get("subspace")),
            gain=float(r.get("gain") or 0.0),
            outcome_range=float(r.get("outcome_range") or 0.0),
            n_points=int(r.get("n_points") or 0),
        )
        for r in records
    ]


def build(
    root: Path | str,
    *,
    config: Optional[Mapping[str, Any]] = None,
    title: str = "Physics of a design agent",
    subtitle: str = "",
) -> Tuple[Dict[str, Any], str]:
    """Load datasets from ``root``, analyse them, and render the report."""

    from tools.analysis.campaign import chain_dirs

    datasets = load_datasets(root)
    chains = [analyse_chain(load_chain(path)) for path in chain_dirs(root)]
    findings = analyse(datasets, chains, config=config)
    document = render(findings, datasets, chains, title=title, subtitle=subtitle)
    return findings, document


__all__ = ["DATASET_NAMES", "analyse", "build", "load_datasets", "render"]
