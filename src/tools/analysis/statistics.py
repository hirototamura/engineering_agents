"""Dependency-light inference for design-loop experiments (numpy only).

The project ships numpy but not scipy, and the analysis needs to stay runnable
in the same environment as the simulator, so the handful of estimators used by
the report are implemented here directly. Each one is small enough to read and
is unit-tested against closed-form cases.

A note on what the uncertainty *is*. The plant is deterministic given its
config: replaying a design under a different ``--seed`` reproduces the outcome
bit for bit (verified in :func:`tools.analysis.experiments.seed_replicates`).
There is therefore no sampling noise to bootstrap over within a design point.
The estimators below are applied across *design points* and *scenario
conditions* -- the populations that genuinely vary -- and never to manufacture
error bars over replicate runs of one deterministic configuration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

DEFAULT_RESAMPLES = 10_000
DEFAULT_SEED = 20260829


# --------------------------------------------------------------------------- #
# interval estimation
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BootstrapInterval:
    """Percentile bootstrap interval for a scalar statistic."""

    estimate: float
    low: float
    high: float
    level: float
    resamples: int

    def as_dict(self) -> Dict[str, float]:
        return {
            "estimate": self.estimate,
            "low": self.low,
            "high": self.high,
            "level": self.level,
            "resamples": float(self.resamples),
        }

    def __str__(self) -> str:  # pragma: no cover - display only
        pct = int(round(self.level * 100))
        return f"{self.estimate:.4g} [{self.low:.4g}, {self.high:.4g}] ({pct}% CI)"


def bootstrap_statistic(
    values: Sequence[float],
    statistic: Callable[[np.ndarray], float],
    *,
    level: float = 0.95,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> BootstrapInterval:
    """Percentile bootstrap of an arbitrary statistic over ``values``."""

    data = np.asarray(list(values), dtype=float)
    data = data[np.isfinite(data)]
    if data.size == 0:
        return BootstrapInterval(math.nan, math.nan, math.nan, level, 0)
    point = float(statistic(data))
    if data.size == 1:
        return BootstrapInterval(point, point, point, level, 0)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, data.size, size=(resamples, data.size))
    draws = np.array([statistic(data[row]) for row in idx], dtype=float)
    alpha = (1.0 - level) / 2.0
    low, high = np.quantile(draws, [alpha, 1.0 - alpha])
    return BootstrapInterval(point, float(low), float(high), level, resamples)


def bootstrap_mean(
    values: Sequence[float],
    *,
    level: float = 0.95,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> BootstrapInterval:
    """Percentile bootstrap interval for the mean."""

    return bootstrap_statistic(
        values, lambda arr: float(arr.mean()), level=level, resamples=resamples, seed=seed
    )


# --------------------------------------------------------------------------- #
# two-sample comparison
# --------------------------------------------------------------------------- #
def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    """Non-parametric effect size in ``[-1, 1]``.

    ``P(a > b) - P(a < b)``. Unlike a standardised mean difference it needs no
    distributional assumption and is unaffected by the heavy saturation at 0 and
    at full crew that dominates these outcomes.
    """

    x = np.asarray(list(a), dtype=float)
    y = np.asarray(list(b), dtype=float)
    x = x[np.isfinite(x)]
    y = y[np.isfinite(y)]
    if x.size == 0 or y.size == 0:
        return math.nan
    diff = x[:, None] - y[None, :]
    return float((np.sign(diff)).sum() / (x.size * y.size))


def cliffs_delta_magnitude(delta: float) -> str:
    """Romano et al. (2006) thresholds, for reporting only."""

    size = abs(delta)
    if not math.isfinite(size):
        return "undefined"
    if size < 0.147:
        return "negligible"
    if size < 0.33:
        return "small"
    if size < 0.474:
        return "medium"
    return "large"


@dataclass(frozen=True)
class PermutationResult:
    observed: float
    p_value: float
    permutations: int
    exact: bool

    def as_dict(self) -> Dict[str, float]:
        return {
            "observed": self.observed,
            "p_value": self.p_value,
            "permutations": float(self.permutations),
            "exact": float(self.exact),
        }


def permutation_test(
    a: Sequence[float],
    b: Sequence[float],
    *,
    statistic: Optional[Callable[[np.ndarray, np.ndarray], float]] = None,
    permutations: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> PermutationResult:
    """Two-sided permutation test on the difference in means by default.

    The p-value uses the ``(hits + 1) / (permutations + 1)`` correction so it is
    never reported as exactly zero.
    """

    stat = statistic or (lambda u, v: float(u.mean() - v.mean()))
    x = np.asarray(list(a), dtype=float)
    y = np.asarray(list(b), dtype=float)
    x = x[np.isfinite(x)]
    y = y[np.isfinite(y)]
    if x.size == 0 or y.size == 0:
        return PermutationResult(math.nan, math.nan, 0, False)
    observed = stat(x, y)
    pool = np.concatenate([x, y])
    n = x.size
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(permutations):
        rng.shuffle(pool)
        if abs(stat(pool[:n], pool[n:])) >= abs(observed) - 1e-12:
            hits += 1
    return PermutationResult(
        observed=float(observed),
        p_value=(hits + 1) / (permutations + 1),
        permutations=permutations,
        exact=False,
    )


# --------------------------------------------------------------------------- #
# logistic response surface
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LogisticFit:
    """Two-parameter logistic ``y = 1 / (1 + exp(-(x - x0) / w))``.

    ``x0`` is the critical point (the 50% response) and ``w`` is the transition
    width. ``1 / (4w)`` is the maximum slope, i.e. the peak susceptibility.
    """

    x0: float
    width: float
    r_squared: float
    rmse: float
    n: int

    def predict(self, x: Sequence[float] | float) -> np.ndarray:
        arr = np.asarray(x, dtype=float)
        z = (arr - self.x0) / max(self.width, 1e-9)
        return 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))

    @property
    def max_slope(self) -> float:
        return 1.0 / (4.0 * max(self.width, 1e-9))

    def as_dict(self) -> Dict[str, float]:
        return {
            "x0": self.x0,
            "width": self.width,
            "max_slope": self.max_slope,
            "r_squared": self.r_squared,
            "rmse": self.rmse,
            "n": float(self.n),
        }


def _logistic_sse(x: np.ndarray, y: np.ndarray, x0: float, width: float) -> float:
    z = (x - x0) / max(width, 1e-9)
    pred = 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))
    return float(np.sum((y - pred) ** 2))


def fit_logistic_response(
    x: Sequence[float],
    y: Sequence[float],
    *,
    refinements: int = 6,
    grid: int = 41,
) -> LogisticFit:
    """Least-squares fit of a 2-parameter logistic to a fractional response.

    Fitted by multi-resolution grid search rather than a gradient method: the
    surface is flat wherever the data saturate, which makes naive gradient
    descent sensitive to its start, and two parameters are cheap to bracket
    exhaustively.
    """

    xs = np.asarray(list(x), dtype=float)
    ys = np.asarray(list(y), dtype=float)
    mask = np.isfinite(xs) & np.isfinite(ys)
    xs, ys = xs[mask], ys[mask]
    if xs.size < 3:
        return LogisticFit(math.nan, math.nan, math.nan, math.nan, int(xs.size))

    span = float(xs.max() - xs.min()) or 1.0
    lo_x0, hi_x0 = float(xs.min()) - 0.5 * span, float(xs.max()) + 0.5 * span
    lo_w, hi_w = math.log(span / 500.0), math.log(span * 2.0)
    best = (math.inf, float(xs.mean()), span / 10.0)

    for _ in range(refinements):
        for x0 in np.linspace(lo_x0, hi_x0, grid):
            for log_w in np.linspace(lo_w, hi_w, grid):
                sse = _logistic_sse(xs, ys, float(x0), float(math.exp(log_w)))
                if sse < best[0]:
                    best = (sse, float(x0), float(math.exp(log_w)))
        _, x0_hat, w_hat = best
        pad_x = (hi_x0 - lo_x0) / (grid - 1) * 2.0
        pad_w = (hi_w - lo_w) / (grid - 1) * 2.0
        lo_x0, hi_x0 = x0_hat - pad_x, x0_hat + pad_x
        lo_w, hi_w = math.log(w_hat) - pad_w, math.log(w_hat) + pad_w

    sse, x0_hat, w_hat = best
    sst = float(np.sum((ys - ys.mean()) ** 2))
    r2 = 1.0 - sse / sst if sst > 0 else math.nan
    return LogisticFit(
        x0=x0_hat,
        width=w_hat,
        r_squared=r2,
        rmse=math.sqrt(sse / xs.size),
        n=int(xs.size),
    )


def r_squared(observed: Sequence[float], predicted: Sequence[float]) -> float:
    obs = np.asarray(list(observed), dtype=float)
    pred = np.asarray(list(predicted), dtype=float)
    mask = np.isfinite(obs) & np.isfinite(pred)
    obs, pred = obs[mask], pred[mask]
    if obs.size == 0:
        return math.nan
    sst = float(np.sum((obs - obs.mean()) ** 2))
    sse = float(np.sum((obs - pred) ** 2))
    return 1.0 - sse / sst if sst > 0 else math.nan


def rmse(observed: Sequence[float], predicted: Sequence[float]) -> float:
    obs = np.asarray(list(observed), dtype=float)
    pred = np.asarray(list(predicted), dtype=float)
    mask = np.isfinite(obs) & np.isfinite(pred)
    obs, pred = obs[mask], pred[mask]
    if obs.size == 0:
        return math.nan
    return float(math.sqrt(np.mean((obs - pred) ** 2)))


def balanced_accuracy(truth: Sequence[bool], predicted: Sequence[bool]) -> float:
    """Unweighted mean of per-class recall.

    Plain accuracy is misleading here for the same reason it is in the opinion
    dynamics literature: one class dominates, so a constant predictor scores
    well. Balancing the classes removes that free lunch.
    """

    t = np.asarray(list(truth), dtype=bool)
    p = np.asarray(list(predicted), dtype=bool)
    if t.size == 0 or t.size != p.size:
        return math.nan
    recalls: List[float] = []
    for label in (True, False):
        mask = t == label
        if not mask.any():
            continue
        recalls.append(float((p[mask] == label).mean()))
    return float(np.mean(recalls)) if recalls else math.nan


# --------------------------------------------------------------------------- #
# survival analysis
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class KaplanMeierCurve:
    """Right-censored survival curve.

    The scorecard already models censoring: a run whose crew never falls below
    the reference horizon is recorded as ``right_censored`` rather than as a
    very large time. Discarding those runs would bias the estimate towards the
    designs that fail, so they enter here as censored observations.
    """

    times: Tuple[float, ...]
    survival: Tuple[float, ...]
    at_risk: Tuple[int, ...]
    events: Tuple[int, ...]
    n: int
    n_events: int

    def median(self) -> float:
        for t, s in zip(self.times, self.survival):
            if s <= 0.5:
                return t
        return math.inf

    def as_dict(self) -> Dict[str, object]:
        return {
            "times": list(self.times),
            "survival": list(self.survival),
            "at_risk": list(self.at_risk),
            "events": list(self.events),
            "n": self.n,
            "n_events": self.n_events,
            "median": self.median(),
        }


def kaplan_meier(
    times: Sequence[float],
    events: Sequence[bool],
) -> KaplanMeierCurve:
    """Kaplan-Meier estimator. ``events[i]`` is False for a censored record."""

    t = np.asarray(list(times), dtype=float)
    e = np.asarray(list(events), dtype=bool)
    mask = np.isfinite(t)
    t, e = t[mask], e[mask]
    if t.size == 0:
        return KaplanMeierCurve((0.0,), (1.0,), (0,), (0,), 0, 0)

    order = np.argsort(t, kind="stable")
    t, e = t[order], e[order]
    out_t: List[float] = [0.0]
    out_s: List[float] = [1.0]
    out_risk: List[int] = [int(t.size)]
    out_ev: List[int] = [0]
    surv = 1.0
    for time in np.unique(t[e]):
        at_risk = int(np.sum(t >= time))
        n_events = int(np.sum((t == time) & e))
        if at_risk <= 0:
            continue
        surv *= 1.0 - n_events / at_risk
        out_t.append(float(time))
        out_s.append(surv)
        out_risk.append(at_risk)
        out_ev.append(n_events)
    return KaplanMeierCurve(
        times=tuple(out_t),
        survival=tuple(out_s),
        at_risk=tuple(out_risk),
        events=tuple(out_ev),
        n=int(t.size),
        n_events=int(e.sum()),
    )


@dataclass(frozen=True)
class LogRankResult:
    statistic: float
    p_value: float
    observed_a: float
    expected_a: float

    def as_dict(self) -> Dict[str, float]:
        return {
            "statistic": self.statistic,
            "p_value": self.p_value,
            "observed_a": self.observed_a,
            "expected_a": self.expected_a,
        }


def _chi2_sf_1df(x: float) -> float:
    """Upper tail of chi-square with one degree of freedom, via ``erfc``."""

    if not math.isfinite(x) or x <= 0:
        return 1.0
    return math.erfc(math.sqrt(x / 2.0))


def log_rank_test(
    times_a: Sequence[float],
    events_a: Sequence[bool],
    times_b: Sequence[float],
    events_b: Sequence[bool],
) -> LogRankResult:
    """Two-group log-rank test (one degree of freedom)."""

    ta = np.asarray(list(times_a), dtype=float)
    ea = np.asarray(list(events_a), dtype=bool)
    tb = np.asarray(list(times_b), dtype=float)
    eb = np.asarray(list(events_b), dtype=bool)
    if ta.size == 0 or tb.size == 0:
        return LogRankResult(math.nan, math.nan, math.nan, math.nan)

    all_events = np.unique(np.concatenate([ta[ea], tb[eb]]))
    obs_a = exp_a = var = 0.0
    for time in all_events:
        n_a = float(np.sum(ta >= time))
        n_b = float(np.sum(tb >= time))
        n = n_a + n_b
        d_a = float(np.sum((ta == time) & ea))
        d_b = float(np.sum((tb == time) & eb))
        d = d_a + d_b
        if n <= 1 or d <= 0:
            continue
        obs_a += d_a
        exp_a += d * n_a / n
        var += d * (n_a / n) * (n_b / n) * ((n - d) / (n - 1.0))
    if var <= 0:
        return LogRankResult(0.0, 1.0, obs_a, exp_a)
    stat = (obs_a - exp_a) ** 2 / var
    return LogRankResult(stat, _chi2_sf_1df(stat), obs_a, exp_a)


# --------------------------------------------------------------------------- #
# response-surface derivatives
# --------------------------------------------------------------------------- #
def central_difference(
    x: Sequence[float],
    y: Sequence[float],
) -> Tuple[np.ndarray, np.ndarray]:
    """``dy/dx`` on an ordered, possibly non-uniform grid.

    Returns the interior abscissae and the central-difference slope there. This
    is the discrete susceptibility of a deterministic response surface: with no
    replicate noise to take a variance over, the derivative is what peaks at a
    transition.
    """

    xs = np.asarray(list(x), dtype=float)
    ys = np.asarray(list(y), dtype=float)
    order = np.argsort(xs, kind="stable")
    xs, ys = xs[order], ys[order]
    if xs.size < 3:
        return np.array([]), np.array([])
    dx = xs[2:] - xs[:-2]
    dy = ys[2:] - ys[:-2]
    with np.errstate(divide="ignore", invalid="ignore"):
        slope = np.where(dx != 0, dy / dx, np.nan)
    return xs[1:-1], slope


def pearson(a: Sequence[float], b: Sequence[float]) -> float:
    x = np.asarray(list(a), dtype=float)
    y = np.asarray(list(b), dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if x.size < 2 or x.std() == 0 or y.std() == 0:
        return math.nan
    return float(np.corrcoef(x, y)[0, 1])


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    """Rank correlation, with average ranks for ties."""

    x = np.asarray(list(a), dtype=float)
    y = np.asarray(list(b), dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if x.size < 2:
        return math.nan
    return pearson(_average_ranks(x), _average_ranks(y))


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="stable")
    ranks = np.empty(values.size, dtype=float)
    ranks[order] = np.arange(1, values.size + 1, dtype=float)
    for value in np.unique(values):
        mask = values == value
        if mask.sum() > 1:
            ranks[mask] = ranks[mask].mean()
    return ranks


def summarise(values: Iterable[float]) -> Dict[str, float]:
    arr = np.asarray([v for v in values], dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"n": 0.0, "mean": math.nan, "sd": math.nan, "min": math.nan, "max": math.nan}
    return {
        "n": float(arr.size),
        "mean": float(arr.mean()),
        "sd": float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
        "median": float(np.median(arr)),
        "min": float(arr.min()),
        "max": float(arr.max()),
    }


__all__ = [
    "BootstrapInterval",
    "KaplanMeierCurve",
    "LogRankResult",
    "LogisticFit",
    "PermutationResult",
    "balanced_accuracy",
    "bootstrap_mean",
    "bootstrap_statistic",
    "central_difference",
    "cliffs_delta",
    "cliffs_delta_magnitude",
    "fit_logistic_response",
    "kaplan_meier",
    "log_rank_test",
    "pearson",
    "permutation_test",
    "r_squared",
    "rmse",
    "spearman",
    "summarise",
]
