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

OUTCOME_KEYS = (
    "crew_initial",
    "crew_remaining",
    "critical_step_count",
    "warning_step_count",
    "peak_co2_storage_kg",
    "min_o2_storage_kg",
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
        "constraint_status": constraints.get("constraint_status"),
        "mass_kg": constraints.get("total_mass_kg"),
        "volume_m3": constraints.get("total_volume_m3"),
        "cost_musd": constraints.get("total_cost_musd"),
    }
    for key in OUTCOME_KEYS:
        if outcome.get(key) is not None:
            view[key] = outcome.get(key)
    view["physics_gate"] = outcome.get("physics_gate_status") or (
        "passed" if outcome.get("physics_gate_passed") else None
    )
    if record.get("error"):
        view["error"] = record["error"]
    return view


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


def build_design_state(
    *,
    baseline_outcome: Mapping[str, Any],
    theory: Mapping[str, Any],
    features: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    scenario_config: Mapping[str, Any],
    decisions_left: int,
    candidate_budget_left: int,
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
    return {
        "baseline": baseline,
        "installed_capacity": _installed(scenario_config),
        "theoretical_capacity": _capacity_need(theory),
        "candidates": views,
        "current_best": current_best(candidates),
        "decisions_left": max(0, int(decisions_left)),
        "remaining_candidate_budget": max(0, int(candidate_budget_left)),
        "decision_needed": "refine_or_finish" if views else "first_candidate",
    }


__all__ = [
    "FIELD_PRECISION",
    "build_design_state",
    "candidate_hash",
    "current_best",
    "find_duplicate",
    "normalize_fields",
]
