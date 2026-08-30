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
from tools.analysis.copy import DEFAULT_SUBTITLE, DEFAULT_TITLE, strings_for
from tools.analysis.design_space import budget_limits, capacity_bounds
from tools.analysis.loop_dynamics import (
    ARCHETYPE_DESCRIPTIONS,
    ChainDynamics,
    analyse_chain,
    archetype_distribution,
    controllability,
    effective_gain,
    from_records,
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
.lang { font-size: 13px; color: var(--muted); margin: 0 0 14px; }
.lang a { color: var(--accent); text-decoration: none; }
.lang [aria-current="page"] { color: var(--ink); font-weight: 600; }
html[lang="ja"] body {
  font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans CJK JP",
               "Yu Gothic", "YuGothic", "WenQuanYi Micro Hei", sans-serif;
  line-height: 1.75;
}
html[lang="ja"] .kpi .l, html[lang="ja"] th {
  text-transform: none;
  letter-spacing: 0.02em;
}
"""


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _fmt(value: Any, digits: int = 3, *, yes: str = "yes", no: str = "no") -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return yes if value else no
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


def _figure(svg: str, number: int, title: str, caption: str, *, prefix: str = "Figure") -> str:
    return (
        f"<figure>{svg}"
        f"<figcaption><b>{_esc(prefix)} {number}. {_esc(title)}</b> {_esc(caption)}</figcaption>"
        f"</figure>"
    )


def _lang_nav(lang: str, t: Mapping[str, Any], peer_href: Optional[str]) -> str:
    if not peer_href:
        return ""
    if lang == "ja":
        current = t["lang_ja"]
        other = f'<a href="{_esc(peer_href)}">{_esc(t["lang_en"])}</a>'
        return f'<nav class="lang">{other} · <span aria-current="page">{_esc(current)}</span></nav>'
    current = t["lang_en"]
    other = f'<a href="{_esc(peer_href)}">{_esc(t["lang_ja"])}</a>'
    return f'<nav class="lang"><span aria-current="page">{_esc(current)}</span> · {other}</nav>'


def _pct(value: Optional[float], digits: int = 0) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return f"{value * 100:.{digits}f}%"


def render(
    findings: Mapping[str, Any],
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    chains: Sequence[ChainDynamics],
    *,
    title: str = "",
    subtitle: str = "",
    lang: str = "en",
    peer_href: Optional[str] = None,
) -> str:
    """Assemble the full HTML report from findings, datasets and figures."""

    t = strings_for(lang)
    if not title:
        title = DEFAULT_TITLE[lang]
    if not subtitle:
        subtitle = DEFAULT_SUBTITLE[lang]

    def fmt(value: Any, digits: int = 3) -> str:
        return _fmt(value, digits, yes=str(t["yes"]), no=str(t["no"]))

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
    profile_names: Mapping[str, str] = t.get("profile_names") or {}
    model_notes: Mapping[str, str] = t.get("model_notes") or {}

    parts: List[str] = []
    figure_no = 0

    def add_figure(svg: str, title_: str, caption: str) -> None:
        nonlocal figure_no
        figure_no += 1
        parts.append(_figure(svg, figure_no, title_, caption, prefix=str(t["figure_prefix"])))

    lightest = surf.get("lightest_full_survival") or {}
    budgets = surf.get("budgets") or {}
    mass_ratio = surf.get("mass_overrun_ratio")
    zero_axes = ctrl.get("zero_gain_axes") or []
    archetypes = loop.get("archetypes") or {}
    dominant = max(archetypes.items(), key=lambda kv: kv[1])[0] if archetypes else "—"

    parts.append(
        '<div class="kpis">'
        + _kpi(f"{n_runs:,}", str(t["kpi_simulations"]))
        + _kpi(f"{surf.get('n_full_survival', 0)}/{surf.get('n', 0)}", str(t["kpi_saving"]))
        + _kpi(str(surf.get("n_full_survival_within_budget", 0)),
               str(t["kpi_budget"]),
               "warn" if surf.get("n_full_survival_within_budget") == 0 else "good")
        + _kpi(f"{len(zero_axes)}/{len(ctrl.get('shipped_operating_point') or [])}",
               str(t["kpi_zero_gain"]), "warn" if zero_axes else "")
        + _kpi(dominant, str(t["kpi_archetype"]),
               "warn" if dominant in ("saturating", "frozen") else "good")
        + "</div>"
    )

    parts.append(f"<h2>{_esc(t['h_summary'])}</h2>")
    parts.append(f"<p>{t['summary_intro']}</p>")
    r2_response = (pred.get("models", {}).get("Liebig on response", {}) or {}).get("r_squared")
    parts.append(
        '<div class="key">'
        + t["key1"].format(r2=fmt(r2_response, 3), n=surf.get("n", 0),
                           delta=fmt(collapse.get("max_abs_difference"), 2))
        + "</div>"
    )
    parts.append(
        '<div class="key warn">'
        + t["key2"].format(
            n=surf.get("n", 0),
            n_full=surf.get("n_full_survival", 0),
            n_budget=surf.get("n_full_survival_within_budget", 0),
            mass=fmt(lightest.get("total_mass_kg"), 0),
            mass_ceil=fmt(budgets.get("max_total_mass_kg"), 0),
            over=fmt((mass_ratio or 1) * 100 - 100, 0),
            cost=fmt(lightest.get("total_cost_musd"), 0),
            cost_ceil=fmt(budgets.get("max_total_cost_musd"), 0),
        )
        + "</div>"
    )
    parts.append(
        '<div class="key warn">'
        + t["key3"].format(
            action_share=_pct((ctrl.get("designer_magnitude_share") or {}).get("action")),
            capacity_share=_pct((ctrl.get("designer_magnitude_share") or {}).get("capacity")),
            cosine=fmt((loop.get("turning_cosine") or {}).get("mean"), 2),
        )
        + "</div>"
    )

    parts.append(f"<h2>{_esc(t['h_method'])}</h2>")
    parts.append(f"<p>{t['method_p1']}</p>")
    parts.append(f"<p>{t['method_p2']}</p>")
    if t.get("method_figures_note"):
        parts.append(f"<p>{t['method_figures_note']}</p>")
    size = findings.get("dataset_sizes") or {}
    ds_keys = (
        "seed_replicates", "response_surface", "one_at_a_time",
        "one_at_a_time_relieved", "crew_scaling", "iso_ray", "chains",
    )
    ds_rows = [
        [row[0], size.get(key, 0), row[1], row[2]]
        for key, row in zip(ds_keys, t["datasets"])
    ]
    parts.append(_table(
        [str(t["th_dataset"]), str(t["th_runs"]), str(t["th_varies"]), str(t["th_answers"])],
        ds_rows,
        numeric=(1,),
    ))

    parts.append(f"<h3>{_esc(t['h_uncertainty'])}</h3>")
    spreads = det.get("spreads") or {}
    parts.append("<p>" + t["p_uncertainty"].format(
        n_seeds=det.get("n_seeds", 0),
        score_spread=fmt(spreads.get("evaluation_score"), 6),
        crew_spread=fmt(spreads.get("crew_remaining"), 6),
    ) + "</p>")
    add_figure(
        figures.fig_mass_balance(all_rows),
        str(t["fig_mass_title"]),
        t["fig_mass_caption"].format(
            passed=phys.get("gate_passed", 0), total=phys.get("gate_total", 0),
        ),
    )

    parts.append(f"<h2>{_esc(t['h_order'])}</h2>")
    parts.append(f"<p>{t['p_order']}</p>")
    add_figure(
        figures.fig_phase_diagram(surface),
        str(t["fig_phase_title"]),
        str(t["fig_phase_caption"]),
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
        str(t["fig_crit_title"]),
        str(t["fig_crit_caption"]),
    )
    parts.append(_table(
        [str(t["th_crit_axis"]), str(t["th_rho_star"]), str(t["th_width"]),
         str(t["th_peak"]), str(t["th_r2"])],
        [
            [profile_names.get(name, name), fmt(fit.x0, 3), fmt(fit.width, 3),
             fmt(fit.max_slope, 2), fmt(fit.r_squared, 3)]
            for name, fit in fits.items()
        ],
        numeric=(1, 2, 3, 4),
    ))

    parts.append(f"<h3>{_esc(t['h_collapse'])}</h3>")
    parts.append("<p>" + t["p_collapse"].format(
        max_abs=fmt(collapse.get("max_abs_difference"), 2),
        mean_abs=fmt(collapse.get("mean_abs_difference"), 3),
        n_paired=collapse.get("n_paired", 0),
        corr=fmt(collapse.get("correlation"), 3),
    ) + "</p>")
    add_figure(
        figures.fig_crew_scaling(
            (collapse.get("iso_ray_profile", {}).get("x", []),
             collapse.get("iso_ray_profile", {}).get("y", [])),
            (collapse.get("crew_profile", {}).get("x", []),
             collapse.get("crew_profile", {}).get("y", [])),
        ),
        str(t["fig_collapse_title"]),
        str(t["fig_collapse_caption"]),
    )

    parts.append(f"<h2>{_esc(t['h_steer'])}</h2>")
    controls = [
        _c for _c in _controls_from(ctrl.get("shipped_operating_point") or [])
    ]
    add_figure(
        figures.fig_controllability(
            controls, ctrl.get("designer_magnitude_share") or {}
        ),
        str(t["fig_ctrl_title"]),
        str(t["fig_ctrl_caption"]),
    )
    span = ctrl.get("action_axis_span") or {}
    n_out = len(span.get("distinct_outcomes") or [])
    plural = "" if lang == "ja" or n_out == 1 else "s"
    parts.append("<p>" + t["p_span"].format(
        n_mult=len(span.get("multipliers") or []),
        lo=fmt(min(span.get("multipliers") or [1]), 2),
        hi=fmt(max(span.get("multipliers") or [1]), 2),
        n_out=n_out,
        plural=plural,
        outcomes=", ".join(fmt(v, 2) for v in (span.get("distinct_outcomes") or [])),
    ) + "</p>")
    add_figure(
        figures.fig_saturation(list(datasets.get("one_at_a_time") or [])),
        str(t["fig_sat_title"]),
        str(t["fig_sat_caption"]),
    )

    parts.append(f"<h3>{_esc(t['h_state_dep'])}</h3>")
    relieved = {c["axis"]: c for c in (ctrl.get("relieved_operating_point") or [])}
    shipped = {c["axis"]: c for c in (ctrl.get("shipped_operating_point") or [])}
    rows = []
    for axis in sorted(set(shipped) | set(relieved)):
        s_gain = (shipped.get(axis) or {}).get("gain")
        r_gain = (relieved.get(axis) or {}).get("gain")
        rows.append([
            axis.replace("_", " "),
            (shipped.get(axis) or relieved.get(axis) or {}).get("subspace", "—"),
            fmt(s_gain, 3), fmt(r_gain, 3),
        ])
    highlight = [
        i for i, row in enumerate(rows)
        if row[2] == "0" and row[3] not in ("0", "—")
    ]
    parts.append(_table(
        [str(t["th_crit_axis"]), str(t["th_subspace"]),
         str(t["th_gain_shipped"]), str(t["th_gain_relieved"])],
        rows, numeric=(2, 3), highlight=highlight,
    ))
    parts.append(f"<p>{t['p_state_dep']}</p>")

    parts.append(f"<h3>{_esc(t['h_rugged'])}</h3>")
    parts.append("<p>" + t["p_rugged"].format(
        descents=rugged.get("surface_descents", 0),
        transitions=rugged.get("surface_transitions", 0),
        rate=_pct(rugged.get("surface_descent_rate")),
        worst=fmt(rugged.get("surface_worst_descent"), 2),
    ) + "</p>")

    parts.append(f"<h2>{_esc(t['h_loop'])}</h2>")
    add_figure(
        figures.fig_loop_dynamics(chains),
        str(t["fig_loop_title"]),
        str(t["fig_loop_caption"]),
    )
    add_figure(
        figures.fig_archetypes(archetypes, loop.get("n_chains", 0)),
        str(t["fig_arch_title"]),
        str(t["fig_arch_caption"]),
    )
    parts.append(_table(
        [str(t["th_chain"]), str(t["th_iterations"]), str(t["th_archetype"]),
         str(t["th_displacement"]), str(t["th_dsurvival"]),
         str(t["th_cap_share"]), str(t["th_act_share"]), str(t["th_discarded"])],
        [
            [c.chain_id, c.length, c.archetype, fmt(c.total_displacement, 3),
             fmt(c.outcome_change, 3),
             _pct(c.magnitude_share.get("capacity")),
             _pct(c.magnitude_share.get("action")),
             _pct(c.discarded_fraction)]
            for c in chains
        ],
        numeric=(1, 3, 4, 5, 6, 7),
    ))
    parts.append("<p>" + t["p_discarded"].format(
        rate=_pct((loop.get("discarded_fraction") or {}).get("mean")),
    ) + "</p>")

    parts.append(f"<h2>{_esc(t['h_tcl'])}</h2>")
    km = findings.get("_km_curves") or {}
    if km:
        lr = findings.get("survival", {}).get("log_rank") or {}
        annotation = (
            t["log_rank"].format(stat=fmt(lr.get("statistic"), 1), p=fmt(lr.get("p_value"), 4))
            if lr else ""
        )
        add_figure(
            figures.fig_survival_curves(km, annotation),
            str(t["fig_surv_title"]),
            str(t["fig_surv_caption"]),
        )

    parts.append(f"<h2>{_esc(t['h_predictive'])}</h2>")
    models = pred.get("models") or {}
    best_model = (
        max(models.items(), key=lambda kv: kv[1].get("r_squared", -math.inf))[0]
        if models else None
    )
    stars = pred.get("critical_coverage") or {}
    parts.append("<p>" + t["p_predictive"].format(
        n_train=pred.get("n_train", 0),
        n_test=pred.get("n_test", 0),
    ) + "</p>")
    model_rows = [
        [name, fmt(models[name].get("r_squared"), 3), fmt(models[name].get("rmse"), 3),
         fmt(models[name].get("balanced_accuracy"), 3),
         model_notes.get(models[name].get("note", ""), models[name].get("note", ""))]
        for name in MODEL_ORDER if name in models
    ]
    parts.append(_table(
        [str(t["th_model"]), str(t["th_heldout_r2"]), str(t["th_rmse"]),
         str(t["th_ba"]), str(t["th_assumes"])],
        model_rows, numeric=(1, 2, 3),
        highlight=[i for i, row in enumerate(model_rows) if row[0] == best_model],
    ))
    naive = (models.get("Liebig on coverage") or {}).get("r_squared")
    margin_model = (models.get("Liebig on margin") or {}).get("r_squared")
    response_model = (models.get("Liebig on response") or {}).get("r_squared")
    ogs_only = (models.get("OGS only") or {}).get("r_squared")
    parts.append("<p>" + t["p_predictive_result"].format(
        naive=fmt(naive, 3),
        ogs_only=fmt(ogs_only, 3),
        star_ars=fmt(stars.get("ARS"), 2),
        star_ogs=fmt(stars.get("OGS"), 2),
        margin=fmt(margin_model, 3),
        response=fmt(response_model, 3),
    ) + "</p>")
    if pred.get("_predictions"):
        add_figure(
            figures.fig_predictive_law(
                pred["_observed"], pred["_predictions"], models
            ),
            str(t["fig_pred_title"]),
            str(t["fig_pred_caption"]),
        )

    parts.append(f"<h2>{_esc(t['h_cost'])}</h2>")
    add_figure(
        figures.fig_pareto(surface, budgets),
        str(t["fig_pareto_title"]),
        str(t["fig_pareto_caption"]),
    )
    parts.append("<p>" + t["p_cost"].format(
        ars=fmt(lightest.get("ars"), 1),
        ogs=fmt(lightest.get("ogs"), 1),
        rho_ars=fmt(lightest.get("rho_ars"), 2),
        rho_ogs=fmt(lightest.get("rho_ogs"), 2),
        mass=fmt(lightest.get("total_mass_kg"), 0),
        cost=fmt(lightest.get("total_cost_musd"), 0),
        volume=fmt(lightest.get("total_volume_m3"), 1),
        mass_ceil=fmt(budgets.get("max_total_mass_kg"), 0),
        cost_ceil=fmt(budgets.get("max_total_cost_musd"), 0),
        vol_ceil=fmt(budgets.get("max_total_volume_m3"), 0),
    ) + "</p>")

    parts.append(f"<h2>{_esc(t['h_implies'])}</h2>")
    parts.append("<ol>")
    parts.append(f"<li><b>{t['imp1_title']}</b> {t['imp1']}</li>")
    parts.append(f"<li><b>{t['imp2_title']}</b> {t['imp2']}</li>")
    parts.append(f"<li><b>{t['imp3_title']}</b> {t['imp3']}</li>")
    parts.append(
        "<li><b>" + t["imp4_title"] + "</b> "
        + t["imp4"].format(rate=_pct(rugged.get("surface_descent_rate")))
        + "</li>"
    )
    parts.append(
        "<li><b>" + t["imp5_title"] + "</b> "
        + t["imp5"].format(r2=fmt(r2_response, 3))
        + "</li>"
    )
    parts.append("</ol>")

    parts.append(f"<h2>{_esc(t['h_limits'])}</h2>")
    parts.append("<ul>")
    parts.append(f"<li>{t['lim1']}</li>")
    parts.append(f"<li>{t['lim2']}</li>")
    parts.append(f"<li>{t['lim3']}</li>")
    parts.append(f"<li>{t['lim4'].format(n=surf.get('n', 0))}</li>")
    parts.append("</ul>")

    generated = findings.get("generated_utc", "")
    body = "\n".join(parts)
    subtitle_html = f"<p class='sub'>{_esc(subtitle)}</p>" if subtitle else ""
    nav = _lang_nav(lang, t, peer_href)
    return f"""<!DOCTYPE html>
<html lang="{_esc(t['html_lang'])}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title><style>{_CSS}</style></head>
<body><div class="wrap">
<header>{nav}<h1>{_esc(title)}</h1>{subtitle_html}
<p class="sub">{t['generated'].format(generated=_esc(generated), n_runs=f'{n_runs:,}')}
&middot; {t['backend_line']}</p></header>
{body}
<footer>{t['footer']}</footer>
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


CHAIN_DYNAMICS_NAME = "chain_dynamics"
FINDINGS_NAME = "design_loop_analysis.findings.json"


def load_persisted_chains(root: Path | str) -> List[ChainDynamics]:
    """Rebuild loop trajectories from tracked artifacts, without raw run dirs.

    Preference order:

    1. ``datasets/chain_dynamics.json`` — serialised :class:`ChainDynamics`
    2. ``design_loop_analysis.findings.json`` ``loop.chains`` — older checkouts
    """

    root = Path(root)
    tracked = root / "datasets" / f"{CHAIN_DYNAMICS_NAME}.json"
    if tracked.is_file():
        payload = json.loads(tracked.read_text(encoding="utf-8"))
        if isinstance(payload, list) and payload:
            return from_records(payload)
    findings_path = root / FINDINGS_NAME
    if findings_path.is_file():
        payload = json.loads(findings_path.read_text(encoding="utf-8"))
        records = (payload.get("loop") or {}).get("chains") if isinstance(payload, Mapping) else None
        if isinstance(records, list) and records:
            return from_records(records)
    return []


def load_chains(root: Path | str) -> List[ChainDynamics]:
    """Live ``chains/`` directories if present, otherwise the tracked artifact."""

    from tools.analysis.campaign import chain_dirs

    live = chain_dirs(root)
    if live:
        return [analyse_chain(load_chain(path)) for path in live]
    return load_persisted_chains(root)


def save_chain_dynamics(root: Path | str, chains: Sequence[ChainDynamics]) -> Optional[Path]:
    """Write ``datasets/chain_dynamics.json`` so ``report`` needs no raw run dirs."""

    if not chains:
        return None
    path = Path(root) / "datasets" / f"{CHAIN_DYNAMICS_NAME}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([chain.as_dict() for chain in chains], indent=1, default=str),
        encoding="utf-8",
    )
    return path


def load_campaign(root: Path | str, *, config: Optional[Mapping[str, Any]] = None
                  ) -> Tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]], List[ChainDynamics]]:
    """Load datasets, reconstruct chains, and compute findings.

    Raw ``chains/`` run directories are git-ignored. A fresh checkout still
    rebuilds loop dynamics from the tracked ``chain_dynamics`` artifact (or,
    failing that, from ``findings.json``).
    """

    datasets = load_datasets(root)
    chains = load_chains(root)
    findings = analyse(datasets, chains, config=config)
    return findings, datasets, chains


def build(
    root: Path | str,
    *,
    config: Optional[Mapping[str, Any]] = None,
    title: str = "",
    subtitle: str = "",
    lang: str = "en",
    peer_href: Optional[str] = None,
) -> Tuple[Dict[str, Any], str]:
    """Load datasets from ``root``, analyse them, and render the report."""

    findings, datasets, chains = load_campaign(root, config=config)
    document = render(
        findings, datasets, chains,
        title=title, subtitle=subtitle, lang=lang, peer_href=peer_href,
    )
    return findings, document


def sibling_report_path(path: Path, lang: str) -> Path:
    """English report ``foo.html`` pairs with Japanese ``foo.ja.html``."""

    path = Path(path)
    if lang == "ja":
        if path.name.endswith(".ja.html"):
            return path
        return path.with_name(path.stem + ".ja.html")
    if path.name.endswith(".ja.html"):
        return path.with_name(path.name[: -len(".ja.html")] + ".html")
    return path


__all__ = [
    "CHAIN_DYNAMICS_NAME",
    "DATASET_NAMES",
    "FINDINGS_NAME",
    "analyse",
    "build",
    "load_campaign",
    "load_chains",
    "load_datasets",
    "load_persisted_chains",
    "render",
    "save_chain_dynamics",
    "sibling_report_path",
]
