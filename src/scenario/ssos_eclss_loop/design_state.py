"""The one page of current state a design decision is made from (spec §6).

The tool-use loop handed the model its own history back on every turn, so it
had to re-read what it had already done to know where it was -- and in the
observed runs it did not: it re-ran the same constraint check across seven
turns and still finished without a second candidate.

This module builds the alternative. Before each decision the designer is given
a freshly assembled picture of where the design stands: what the baseline run
showed, what capacity the crew actually needs, every candidate tried so far
with its verified outcome, which one currently leads, and how much budget
remains. Nothing has to be remembered, so nothing can be forgotten.

Candidate identity lives here too. Two proposals that name the same machine
are the same candidate however they were written, so the second one costs a
decision but not a simulation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

from scenario.ssos_eclss_loop.design_eval import rank_candidates
from scenario.ssos_eclss_loop.design_variables import CAPACITY_KEYS

# Two capacities that differ by less than this are the same machine. Rounding
# before hashing is what makes "23.92" and "23.920000000000002" one candidate.
FIELD_PRECISION = 6

# How many people came back, and nothing else raw. Dwell counts, peaks and
# minima are no longer shown on their own: they are marked inside the score,
# and shown twice they compete with it. A run where the peak was identical
# across every design ever built -- because it happened while the machine was
# switched off -- was read as "still not enough capacity" thirty-eight times in
# a row, which is what showing an unmoving number as a design metric buys.
OUTCOME_KEYS = (
    "crew_initial",
    "crew_remaining",
)


OBJECTIVE_NOTE = (
    "Two things decide the ranking, in this order: every occupant must come back "
    "alive, then the scorecard. Nothing else is compared -- mass, cost and time "
    "spent in the warning bands are marked inside the score, so a heavier machine "
    "has to earn its weight back on some other axis. Read 'worst_axes' to see "
    "where a design lost its marks; a low score is a statement about what to "
    "change, not a request for more capacity."
)


def normalize_fields(fields: Mapping[str, Any]) -> Dict[str, float]:
    """Canonical form of a capacity proposal: known keys, sorted, rounded."""
    normalized: Dict[str, float] = {}
    for key in sorted(fields):
        if key not in CAPACITY_KEYS:
            continue
        value = fields[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        normalized[key] = round(float(value), FIELD_PRECISION)
    return normalized


def candidate_hash(fields: Mapping[str, Any]) -> str:
    """Identity of a machine, independent of how the proposal was written."""
    canonical = json.dumps(normalize_fields(fields), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def find_duplicate(
    candidates: Sequence[Mapping[str, Any]], fields: Mapping[str, Any]
) -> Optional[Mapping[str, Any]]:
    """The already-simulated candidate that is this same machine, if any."""
    wanted = candidate_hash(fields)
    for record in candidates:
        if record.get("candidate_hash") == wanted:
            return record
    return None


def _installed(scenario_config: Mapping[str, Any]) -> Dict[str, float]:
    plant = scenario_config.get("plant_sim")
    plant = plant if isinstance(plant, Mapping) else {}
    out: Dict[str, float] = {}
    for key in CAPACITY_KEYS:
        node: Any = scenario_config
        for part in key.split("."):
            node = node.get(part) if isinstance(node, Mapping) else None
        if isinstance(node, (int, float)) and not isinstance(node, bool):
            out[key] = float(node)
    return out


def _candidate_view(record: Mapping[str, Any]) -> Dict[str, Any]:
    """One candidate, as much as a design decision needs and no more."""
    outcome = record.get("outcome") if isinstance(record.get("outcome"), Mapping) else {}
    constraints = (
        record.get("constraint_evaluation")
        if isinstance(record.get("constraint_evaluation"), Mapping)
        else {}
    )
    view: Dict[str, Any] = {
        "candidate_id": record.get("candidate_id"),
        "fields": normalize_fields(record.get("fields") or {}),
        "simulated": bool(record.get("simulated")),
        # Kept because it says whether the machine can be built at all, which is
        # not a matter of degree and so cannot be a score.
        "constraint_status": constraints.get("constraint_status"),
    }
    for key in OUTCOME_KEYS:
        if outcome.get(key) is not None:
            view[key] = outcome.get(key)
    view["physics_gate"] = outcome.get("physics_gate_status") or (
        "passed" if outcome.get("physics_gate_passed") else None
    )
    view["scorecard"] = _scorecard(outcome)
    if record.get("error"):
        view["error"] = record["error"]
    return view


def _scorecard(outcome: Mapping[str, Any]) -> Dict[str, Any]:
    """The marks, and where they were lost.

    The total says a design is worse; the breakdown says why. Without the
    second half the only move available is to make the machine bigger, which
    is what a designer given only a total actually does.
    """
    compact = outcome.get("evaluation_compact") if isinstance(outcome, Mapping) else None
    if not isinstance(compact, Mapping):
        return {"status": "unscored"}
    total = compact.get("score")
    maximum = compact.get("max_score")
    card: Dict[str, Any] = {
        "status": compact.get("status"),
        "score": total,
        "max_score": maximum,
    }
    if isinstance(total, (int, float)) and isinstance(maximum, (int, float)) and maximum:
        # Runs can be marked out of 100 or out of 90, so the share is the part
        # that compares between them.
        card["percent"] = round(100.0 * float(total) / float(maximum), 2)
    axes = compact.get("axes")
    if isinstance(axes, Mapping):
        card["axes"] = {
            name: {"score": axis.get("score"), "max": axis.get("max")}
            for name, axis in axes.items()
            if isinstance(axis, Mapping)
        }
    lost = compact.get("points_lost")
    if isinstance(lost, list) and lost:
        card["worst_axes"] = lost[:3]
    return card


def current_best(candidates: Sequence[Mapping[str, Any]]) -> Optional[str]:
    """The leading candidate under the adoption ranking, if anything ran."""
    simulated = [dict(record) for record in candidates if record.get("simulated")]
    if not simulated:
        return None
    return rank_candidates(simulated)[0].get("candidate_id")


def _bottlenecks(theory: Mapping[str, Any]) -> List[str]:
    """Subsystems that cannot meet the crew's demand, worst shortfall first."""
    subsystems = theory.get("subsystems") if isinstance(theory, Mapping) else None
    if not isinstance(subsystems, Mapping):
        return []
    short = [
        (name, float(body.get("coverage_ratio", 1.0) or 0.0))
        for name, body in subsystems.items()
        if isinstance(body, Mapping)
        and isinstance(body.get("coverage_ratio"), (int, float))
        and float(body["coverage_ratio"]) < 1.0
    ]
    return [name for name, _ in sorted(short, key=lambda item: item[1])]


def _capacity_need(theory: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Required versus installed, per subsystem, with nothing else attached."""
    subsystems = theory.get("subsystems") if isinstance(theory, Mapping) else None
    if not isinstance(subsystems, Mapping):
        return {}
    wanted = (
        "required_kg_day",
        "required_l_operation",
        "required_nameplate_kg_day",
        "effective_capacity_kg_day",
        "nameplate_kg_day",
        "coverage_ratio",
    )
    out: Dict[str, Dict[str, Any]] = {}
    for name, body in subsystems.items():
        if not isinstance(body, Mapping):
            continue
        out[name] = {key: body[key] for key in wanted if body.get(key) is not None}
    return out


CHAIN_MEMORY_NOTE = (
    "Bounded evidence from earlier iterations of this chain, not a substitute for "
    "the current run. Keep or improve on 'best_full_survival' unless the evidence "
    "above gives a reason to explore elsewhere, name all three design variables so "
    "a later iteration cannot silently drop one, and if you size ARS or OGS below "
    "'theoretical_floor', say why the crew still survives on less. When "
    "'exploration_directive' is present the chain has stopped making progress: "
    "propose a materially different sizing rather than the best or most recent "
    "one again."
)


def _chain_memory_view(chain_memory: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """The memory as the decision should read it, or nothing.

    A memory that could not be loaded is left out rather than shown: an error
    object on the page is one more thing to reason about and says nothing about
    what to build.
    """
    if not isinstance(chain_memory, Mapping) or chain_memory.get("error"):
        return None
    view = {
        key: chain_memory.get(key)
        for key in (
            "updated_after_iteration",
            "theoretical_floor",
            "measured_limits",
            "best_full_survival",
            "last_effective_design",
            "known_bad_patterns",
            "proposal_guidance",
            "exploration_directive",
        )
        if chain_memory.get(key) is not None
    }
    if not view:
        return None
    view["note"] = CHAIN_MEMORY_NOTE
    return view


def build_design_state(
    *,
    baseline_outcome: Mapping[str, Any],
    theory: Mapping[str, Any],
    features: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    scenario_config: Mapping[str, Any],
    decisions_left: int,
    candidate_budget_left: int,
    chain_memory: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the state a single design decision is taken from."""
    baseline: Dict[str, Any] = {
        key: baseline_outcome.get(key)
        for key in OUTCOME_KEYS
        if baseline_outcome.get(key) is not None
    }
    baseline["physics_gate"] = baseline_outcome.get("physics_gate_status") or (
        "passed" if baseline_outcome.get("physics_gate_passed") else None
    )
    baseline["bottlenecks"] = _bottlenecks(theory)
    stress = features.get("subsystem_stress") if isinstance(features, Mapping) else None
    if isinstance(stress, Mapping):
        baseline["subsystem_stress"] = stress

    views = [_candidate_view(record) for record in candidates]
    baseline["scorecard"] = _scorecard(baseline_outcome)
    memory = _chain_memory_view(chain_memory)
    state: Dict[str, Any] = {
        "objective": OBJECTIVE_NOTE,
        "baseline": baseline,
        "installed_capacity": _installed(scenario_config),
        "theoretical_capacity": _capacity_need(theory),
        "candidates": views,
        "current_best": current_best(candidates),
        "decisions_left": max(0, int(decisions_left)),
        "remaining_candidate_budget": max(0, int(candidate_budget_left)),
        "decision_needed": "refine_or_finish" if views else "first_candidate",
    }
    if memory is not None:
        state["chain_memory"] = memory
    return state


__all__ = [
    "CHAIN_MEMORY_NOTE",
    "FIELD_PRECISION",
    "OBJECTIVE_NOTE",
    "build_design_state",
    "candidate_hash",
    "current_best",
    "find_duplicate",
    "normalize_fields",
]
