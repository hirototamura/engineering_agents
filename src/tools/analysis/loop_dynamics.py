"""Order parameters and archetypes for a design->verify chain.

A chain is a trajectory in design space. This module gives it the same
treatment an opinion trajectory gets in the collective-dynamics literature:
reduce it to a few scalar order parameters per step, then classify the whole
trajectory into a small, exhaustive taxonomy.

The order parameters are

``displacement``
    ``||d_k - d_0||`` in log-capacity units: how far the loop has travelled from
    the shipped station.
``step_norm``
    ``||d_k - d_{k-1}||``: how big the k-th move was. A converging search has a
    decaying step norm; a saturating one has a constant step norm and a flat
    outcome, which is the signature of pushing on an axis that does nothing.
``turning angle``
    ``cos(theta_k)`` between consecutive steps. Near ``+1`` the loop marches in
    a fixed direction (the analogue of conviction buildup); near ``-1`` it
    reverses, which is overshoot-and-correct.
``actuation share``
    The fraction of a step's magnitude that lands in each actuation subspace
    (capacity / action / policy). Paired with the measured controllability of
    those subspaces it decides whether a step can move the outcome at all.

The taxonomy deliberately separates *the loop did not move* from *the loop moved
and nothing happened*: they look identical in an outcome plot and have opposite
fixes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from tools.analysis.artifacts import ChainRecord
from tools.analysis.design_space import (
    ACTUATION_AXIS_NAMES,
    SUBSPACES,
    subspace_norms,
)

#: Which actuation subspace a proposal ``change_kind`` belongs to.
SUBSPACE_BY_CHANGE_KIND: Dict[str, str] = {
    "capacity_profile": "capacity",
    "action_profile": "action",
    "service_config": "action",
    "set_parameter": "policy",
    "graph_rewire": "topology",
}

ARCHETYPES: Tuple[str, ...] = (
    "frozen",
    "saturating",
    "converging",
    "overshooting",
    "oscillating",
)

ARCHETYPE_DESCRIPTIONS: Dict[str, str] = {
    "frozen": "no design change is proposed after the first run",
    "saturating": "the loop keeps moving but the outcome never changes",
    "converging": "the outcome improves and the step size decays",
    "overshooting": "the outcome improves after at least one reversal in direction",
    "oscillating": "direction reverses repeatedly without a sustained improvement",
}

_EPS = 1e-12


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


def _norm(a: Sequence[float]) -> float:
    return math.sqrt(_dot(a, a))


@dataclass(frozen=True)
class IterationState:
    """One iteration of a chain, in both design and outcome coordinates."""

    iteration: int
    vector: Dict[str, float]
    survival_fraction: Optional[float]
    evaluation_score: Optional[float]
    rho_min: float
    displacement: float
    step_norm: float
    turning_cosine: Optional[float]
    step_by_subspace: Dict[str, float] = field(default_factory=dict)
    displacement_by_subspace: Dict[str, float] = field(default_factory=dict)
    proposed_kinds: Dict[str, int] = field(default_factory=dict)
    applied_kinds: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "vector": dict(self.vector),
            "survival_fraction": self.survival_fraction,
            "evaluation_score": self.evaluation_score,
            "rho_min": self.rho_min,
            "displacement": self.displacement,
            "step_norm": self.step_norm,
            "turning_cosine": self.turning_cosine,
            "step_by_subspace": dict(self.step_by_subspace),
            "displacement_by_subspace": dict(self.displacement_by_subspace),
            "proposed_kinds": dict(self.proposed_kinds),
            "applied_kinds": dict(self.applied_kinds),
        }


@dataclass(frozen=True)
class ChainDynamics:
    """A chain reduced to its trajectory statistics and its archetype."""

    chain_id: str
    design_mode: Optional[str]
    states: Tuple[IterationState, ...]
    archetype: str
    total_displacement: float
    displacement_by_subspace: Dict[str, float]
    outcome_change: float
    proposed_share: Dict[str, float]
    applied_share: Dict[str, float]
    magnitude_share: Dict[str, float]
    discarded_fraction: float
    verdict: Optional[str]

    @property
    def length(self) -> int:
        return len(self.states)

    def series(self, key: str) -> List[Optional[float]]:
        return [getattr(state, key) for state in self.states]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "design_mode": self.design_mode,
            "length": self.length,
            "archetype": self.archetype,
            "total_displacement": self.total_displacement,
            "displacement_by_subspace": dict(self.displacement_by_subspace),
            "outcome_change": self.outcome_change,
            "proposed_share": dict(self.proposed_share),
            "applied_share": dict(self.applied_share),
            "magnitude_share": dict(self.magnitude_share),
            "discarded_fraction": self.discarded_fraction,
            "verdict": self.verdict,
            "states": [state.as_dict() for state in self.states],
        }


def _kind_counts(changes: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for change in changes:
        kind = str(change.get("change_kind", "unknown"))
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _subspace_share(counts: Mapping[str, int]) -> Dict[str, float]:
    """Fraction of proposed changes landing in each actuation subspace."""

    total = sum(counts.values())
    if total <= 0:
        return {}
    shares: Dict[str, float] = {}
    for kind, count in counts.items():
        subspace = SUBSPACE_BY_CHANGE_KIND.get(kind, "other")
        shares[subspace] = shares.get(subspace, 0.0) + count / total
    return shares


def classify(
    step_norms: Sequence[float],
    turning: Sequence[Optional[float]],
    outcomes: Sequence[Optional[float]],
    *,
    move_tol: float = 1e-6,
    outcome_tol: float = 1e-9,
) -> str:
    """Assign a chain to one of :data:`ARCHETYPES`.

    The classes are mutually exclusive and exhaustive, tested in order. The
    first test is the important one: a loop that proposes nothing and a loop
    that proposes something ineffective are different failures.
    """

    moves = [m for m in step_norms if m is not None]
    if not moves or max(moves) <= move_tol:
        return "frozen"

    values = [v for v in outcomes if v is not None]
    delta = (values[-1] - values[0]) if len(values) >= 2 else 0.0
    improved = delta > outcome_tol
    reversals = sum(1 for c in turning if c is not None and c < 0.0)

    if not improved and abs(delta) <= outcome_tol:
        return "saturating"
    if reversals >= 2:
        return "oscillating"
    if improved and reversals == 1:
        return "overshooting"
    if improved:
        return "converging"
    return "oscillating" if reversals else "saturating"


def analyse_chain(
    chain: ChainRecord,
    *,
    outcome_key: str = "survival_fraction",
) -> ChainDynamics:
    """Reduce a loaded chain to its order parameters and archetype."""

    states: List[IterationState] = []
    vectors: List[Dict[str, float]] = []
    proposed_total: Dict[str, int] = {}
    applied_total: Dict[str, int] = {}
    magnitude_total: Dict[str, float] = {name: 0.0 for name in SUBSPACES}

    def delta(a: Mapping[str, float], b: Mapping[str, float]) -> Dict[str, float]:
        return {name: a.get(name, 0.0) - b.get(name, 0.0) for name in ACTUATION_AXIS_NAMES}

    def ordered(vec: Mapping[str, float]) -> List[float]:
        return [vec.get(name, 0.0) for name in ACTUATION_AXIS_NAMES]

    for index, run in enumerate(chain.iterations):
        vector = run.actuation_vector
        vectors.append(vector)
        from_origin = delta(vector, vectors[0])
        displacement = _norm(ordered(from_origin))
        if index == 0:
            step_norm = 0.0
            turning: Optional[float] = None
            step: Dict[str, float] = {name: 0.0 for name in ACTUATION_AXIS_NAMES}
        else:
            step = delta(vector, vectors[index - 1])
            step_norm = _norm(ordered(step))
            prev = delta(vectors[index - 1], vectors[index - 2]) if index >= 2 else None
            if prev is None or _norm(ordered(prev)) < _EPS or step_norm < _EPS:
                turning = None
            else:
                turning = _dot(ordered(step), ordered(prev)) / (
                    _norm(ordered(prev)) * step_norm
                )

        step_subspace = subspace_norms(step)
        for name, value in step_subspace.items():
            magnitude_total[name] = magnitude_total.get(name, 0.0) + value

        proposed = _kind_counts(run.proposal_changes())
        applied = _kind_counts(chain.applied_changes(index))
        for key, count in proposed.items():
            proposed_total[key] = proposed_total.get(key, 0) + count
        for key, count in applied.items():
            applied_total[key] = applied_total.get(key, 0) + count

        states.append(
            IterationState(
                iteration=index + 1,
                vector=vector,
                survival_fraction=run.survival_fraction,
                evaluation_score=run.evaluation_score,
                rho_min=run.coverage.minimum,
                displacement=displacement,
                step_norm=step_norm,
                turning_cosine=turning,
                step_by_subspace=step_subspace,
                displacement_by_subspace=subspace_norms(from_origin),
                proposed_kinds=proposed,
                applied_kinds=applied,
            )
        )

    outcomes = [getattr(state, outcome_key, None) for state in states]
    values = [v for v in outcomes if v is not None]
    n_proposed = sum(proposed_total.values())
    n_applied = sum(applied_total.values())
    magnitude_sum = sum(magnitude_total.values())

    return ChainDynamics(
        chain_id=chain.chain_id,
        design_mode=chain.iterations[0].design_mode if chain.iterations else None,
        states=tuple(states),
        archetype=classify(
            [state.step_norm for state in states[1:]],
            [state.turning_cosine for state in states],
            outcomes,
        ),
        total_displacement=states[-1].displacement if states else 0.0,
        displacement_by_subspace=(
            dict(states[-1].displacement_by_subspace) if states else {}
        ),
        outcome_change=(values[-1] - values[0]) if len(values) >= 2 else 0.0,
        proposed_share=_subspace_share(proposed_total),
        applied_share=_subspace_share(applied_total),
        magnitude_share=(
            {name: value / magnitude_sum for name, value in magnitude_total.items()}
            if magnitude_sum > 0
            else {name: 0.0 for name in SUBSPACES}
        ),
        discarded_fraction=(1.0 - n_applied / n_proposed) if n_proposed else 0.0,
        verdict=chain.verdict,
    )


def archetype_distribution(chains: Sequence[ChainDynamics]) -> Dict[str, float]:
    """Share of chains in each archetype, over all of :data:`ARCHETYPES`."""

    total = len(chains)
    counts = {name: 0 for name in ARCHETYPES}
    for chain in chains:
        counts[chain.archetype] = counts.get(chain.archetype, 0) + 1
    if total == 0:
        return {name: 0.0 for name in counts}
    return {name: count / total for name, count in counts.items()}


# --------------------------------------------------------------------------- #
# controllability
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AxisControllability:
    """How much the outcome moves per unit of movement along one axis.

    ``gain`` is ``d(outcome) / d(ln value)``, taken as the largest magnitude
    central difference over the sampled range. Using the maximum rather than a
    mean keeps a genuinely effective axis from being averaged away by the flat
    saturated region beyond its transition.
    """

    axis: str
    subspace: str
    gain: float
    outcome_range: float
    n_points: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "axis": self.axis,
            "subspace": self.subspace,
            "gain": self.gain,
            "outcome_range": self.outcome_range,
            "n_points": self.n_points,
        }


def controllability(
    rows: Sequence[Mapping[str, Any]],
    *,
    outcome_key: str = "survival_fraction",
) -> List[AxisControllability]:
    """Per-axis controllability from a one-at-a-time sweep.

    Expects rows carrying the ``axis`` / ``subspace`` / ``multiplier`` labels
    written by :func:`tools.analysis.experiments.one_at_a_time_specs`.
    """

    grouped: Dict[Tuple[str, str], List[Tuple[float, float]]] = {}
    for row in rows:
        axis = row.get("axis")
        subspace = row.get("subspace")
        mult = row.get("multiplier")
        outcome = row.get(outcome_key)
        if axis is None or subspace is None:
            continue
        if not isinstance(mult, (int, float)) or not isinstance(outcome, (int, float)):
            continue
        if mult <= 0:
            continue
        grouped.setdefault((str(axis), str(subspace)), []).append(
            (math.log(float(mult)), float(outcome))
        )

    out: List[AxisControllability] = []
    for (axis, subspace), points in sorted(grouped.items()):
        points.sort()
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        gain = 0.0
        for i in range(1, len(points)):
            dx = xs[i] - xs[i - 1]
            if abs(dx) < _EPS:
                continue
            gain = max(gain, abs((ys[i] - ys[i - 1]) / dx))
        out.append(
            AxisControllability(
                axis=axis,
                subspace=subspace,
                gain=gain,
                outcome_range=(max(ys) - min(ys)) if ys else 0.0,
                n_points=len(points),
            )
        )
    return sorted(out, key=lambda item: item.gain, reverse=True)


def effective_gain(
    shares: Mapping[str, float],
    controls: Sequence[AxisControllability],
) -> Dict[str, float]:
    """Actuation share times subspace controllability, per subspace.

    This is the quantity that decides whether a design loop is closed in
    practice. A designer can propose vigorously (large share) on an axis the
    plant ignores (zero gain) and the product is still zero -- the update lies
    in the kernel of the performance map.
    """

    best: Dict[str, float] = {}
    for control in controls:
        best[control.subspace] = max(best.get(control.subspace, 0.0), control.gain)
    return {
        subspace: float(share) * best.get(subspace, 0.0)
        for subspace, share in shares.items()
    }


__all__ = [
    "ARCHETYPES",
    "ARCHETYPE_DESCRIPTIONS",
    "AxisControllability",
    "ChainDynamics",
    "IterationState",
    "SUBSPACE_BY_CHANGE_KIND",
    "analyse_chain",
    "archetype_distribution",
    "classify",
    "controllability",
    "effective_gain",
]
