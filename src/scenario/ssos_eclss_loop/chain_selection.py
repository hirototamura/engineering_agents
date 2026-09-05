"""The one design a chain of iterations answers with.

An iterating run is allowed to wander. A sizing that loses occupants, or one
that cannot be manufactured, may still be worth building and simulating,
because the next iteration reasons from what it did — that is how the chain
finds anything. What must not happen is that the wandering decides the answer.

Without this module a chain ends by comparing the first run's crew count with
the last one's, and adopts whatever the last iteration happened to be holding.
A design that saved every occupant in iteration 1 can be replaced in
iteration 2 by one that does not, and then it is gone: no artifact names it,
nothing points at it, and the chain reports the loss as its result.

So the answer is chosen once, at the end, over the machines that actually flew.
Intra-run candidates that were ranked but never installed are search notes, not
answers. Exploration stays free; adoption does not. The design that comes
back must keep the whole crew alive and be buildable — over budget is allowed
through as ``provisional_final``, because paying for it is a decision a human
makes. If nothing in the whole chain qualifies, that is the answer: nothing
qualified. The best of a losing set is not promoted to a result.

One precondition, in :func:`scoring_bar_drift`. Candidates from different
iterations can only be ranked against each other if they sat the same exam.
If a threshold, the crew size, the run length or the backend moved partway
through, the numbers are not comparable and the chain says so instead of
ranking them.

The comparison is between iterations, not against the shipped scenario file. A
chain deliberately run at six occupants over eight steps has moved every one of
those numbers away from the scenario and is still perfectly self-consistent;
what would break it is moving them again halfway through.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import yaml

from scenario.ssos_eclss_loop.design_constraints import DesignConstraints
from scenario.ssos_eclss_loop.design_eval import (
    STATUS_APPROVED,
    STATUS_PROVISIONAL,
    STATUS_REJECTED,
    evaluate_run_outcome,
    mark_final_eligibility,
    rank_candidates,
    rank_rationale,
    select_final_candidate,
)
from scenario.ssos_eclss_loop.design_variables import read_capacity_fields

CHAIN_FINAL_ANSWER_FILENAME = "chain_final_answer.json"

# Nothing was ranked, because ranking would have compared runs held to
# different standards. Distinct from "ranked and nothing qualified".
STATUS_NOT_COMPARABLE = "not_comparable"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


# What a candidate is judged against. Two runs that disagree on any of these
# were not asked the same question, so their results are not comparable, no
# matter how similar the numbers look.
SCORING_BAR_KEYS = (
    "thresholds",
    "crew_initial",
    "steps",
    "backend",
    "inject_failures",
)


def scoring_bar(run_dir: Path) -> Optional[Dict[str, Any]]:
    """The standard one run was held to, or ``None`` if it did not record one."""
    summary = _read_json(Path(run_dir) / "summary.json")
    if summary is None:
        return None
    return {key: summary.get(key) for key in SCORING_BAR_KEYS}


def scoring_bar_drift(run_dirs: Sequence[Path]) -> List[Dict[str, Any]]:
    """Iterations that were not held to the same standard as the first one.

    A run that recorded no standard at all is reported too. Silence is not
    evidence that nothing moved, and ranking against an unknown bar is the
    thing this check exists to prevent.
    """
    drifted: List[Dict[str, Any]] = []
    reference: Optional[Dict[str, Any]] = None
    reference_iteration = 0
    for index, run_dir in enumerate(run_dirs, start=1):
        bar = scoring_bar(run_dir)
        if bar is None:
            drifted.append(
                {
                    "iteration": index,
                    "run_dir": str(run_dir),
                    "reason": "the run did not record what it was scored against",
                }
            )
            continue
        if reference is None:
            reference, reference_iteration = bar, index
            continue
        differing = [key for key in SCORING_BAR_KEYS if bar.get(key) != reference.get(key)]
        if differing:
            drifted.append(
                {
                    "iteration": index,
                    "run_dir": str(run_dir),
                    "reason": (
                        "scored against a different standard than iteration %d"
                        % reference_iteration
                    ),
                    "changed": differing,
                    "expected": {key: reference.get(key) for key in differing},
                    "found": {key: bar.get(key) for key in differing},
                }
            )
    return drifted


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _constraint_evaluation(
    config: Mapping[str, Any],
    fields: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> Dict[str, Any]:
    """Label the flown machine. Summary stamps win when the config is incomplete."""
    if fields:
        try:
            evaluation = DesignConstraints.from_scenario_config(config).evaluate(fields)
            if evaluation.get("preflight_status") == "valid":
                return evaluation
        except Exception:
            pass
    status = summary.get("constraint_status")
    return {
        "preflight_status": "valid" if status else "invalid",
        "constraint_status": status,
        "total_mass_kg": summary.get("total_mass_kg"),
        "total_volume_m3": summary.get("total_volume_m3"),
        "total_cost_musd": summary.get("total_cost_musd"),
        "design_penalty": summary.get("design_penalty"),
    }


def collect_chain_candidates(run_dirs: Sequence[Path]) -> List[Dict[str, Any]]:
    """The machine each completed iteration actually flew.

    Intra-run candidates that were ranked but never installed are search
    notes. The chain answers with a machine that ran, not one that might have.
    """
    collected: List[Dict[str, Any]] = []
    for index, run_dir in enumerate(run_dirs, start=1):
        run_dir = Path(run_dir)
        summary = _read_json(run_dir / "summary.json")
        if not summary:
            continue
        config = _load_yaml(run_dir / "scenario_config.yaml")
        fields = read_capacity_fields(config) if config else {}
        record = {
            "candidate_id": "flown",
            "label": "iteration %d flown machine" % index,
            "fields": fields,
            "simulated": True,
            "outcome": evaluate_run_outcome(run_dir),
            "constraint_evaluation": _constraint_evaluation(config, fields, summary),
            "iteration": index,
            "iteration_run_dir": str(run_dir),
            "iteration_rank": 1,
            "chain_candidate_id": "i%d/flown" % index,
        }
        collected.append(record)
    return collected


def _chain_baseline(run_dirs: Sequence[Path]) -> Dict[str, Any]:
    """The first flown machine: the station the chain started from."""
    for run_dir in run_dirs:
        summary = _read_json(Path(run_dir) / "summary.json")
        if summary:
            return evaluate_run_outcome(Path(run_dir))
    return {}


def select_chain_final_answer(
    run_dirs: Iterable[Path],
    *,
    require_within_budget: bool = False,
) -> Dict[str, Any]:
    """Choose the one design the whole chain answers with.

    Eligibility is re-derived here rather than trusted from the iteration
    files. Each iteration marked its candidates against its own baseline — the
    design the previous iteration handed it — so "better than baseline" meant
    something different each time. Across the chain there is one reference: the
    station as it was before any of this started.
    """
    run_dirs = [Path(d) for d in run_dirs]
    drift = scoring_bar_drift(run_dirs)
    if drift:
        return {
            "status": STATUS_NOT_COMPARABLE,
            "selected": None,
            "reason": (
                "candidates were not ranked: the standard moved during the chain, so "
                "candidates from different iterations were not answering the same question"
            ),
            "scoring_bar_drift": drift,
            "iterations_considered": len(run_dirs),
            "candidates_considered": 0,
            "ranking": [],
        }

    baseline = _chain_baseline(run_dirs)
    candidates = collect_chain_candidates(run_dirs)
    for record in candidates:
        mark_final_eligibility(
            record,
            baseline_outcome=baseline,
            require_in_bounds=True,
            require_within_budget=require_within_budget,
        )
    ranked = rank_candidates(candidates)
    eligible = [record for record in ranked if record.get("final_eligible")]

    if not eligible:
        # Deliberately not "the best we found". A chain that never produced a
        # design keeping everyone alive has to say that, or the next reader
        # will take the top row as an answer.
        return {
            "status": STATUS_REJECTED,
            "selected": None,
            "reason": (
                "no candidate in the chain keeps every occupant alive within the "
                "engineering bounds; the best observed design is reported for context "
                "and is not an answer"
                if candidates
                else "no candidate was simulated anywhere in the chain"
            ),
            "scoring_bar_drift": [],
            "iterations_considered": len(run_dirs),
            "candidates_considered": len(candidates),
            "best_observed": _row(ranked[0]) if ranked else None,
            "ranking": [_row(record) for record in ranked],
        }

    selection = select_final_candidate(ranked, baseline_outcome=baseline)
    winner = eligible[0]
    runner_up = eligible[1] if len(eligible) > 1 else None
    return {
        "status": selection.get("final_status", STATUS_REJECTED),
        "selected": _row(winner),
        "reason": selection.get("reason"),
        "requires_supervisor_approval": bool(selection.get("requires_supervisor_approval", False)),
        "decided_by": rank_rationale(winner, runner_up),
        "scoring_bar_drift": [],
        "iterations_considered": len(run_dirs),
        "candidates_considered": len(candidates),
        "eligible_count": len(eligible),
        "baseline": baseline,
        "ranking": [_row(record) for record in ranked],
    }


def _row(record: Mapping[str, Any]) -> Dict[str, Any]:
    outcome = record.get("outcome") or {}
    constraints = record.get("constraint_evaluation") or {}
    return {
        "rank": record.get("rank"),
        "chain_candidate_id": record.get("chain_candidate_id"),
        "iteration": record.get("iteration"),
        "iteration_rank": record.get("iteration_rank"),
        "iteration_run_dir": record.get("iteration_run_dir"),
        "candidate_id": record.get("candidate_id"),
        "label": record.get("label"),
        "fields": record.get("fields"),
        "crew_remaining": outcome.get("crew_remaining"),
        "crew_initial": outcome.get("crew_initial"),
        "critical_step_count": outcome.get("critical_step_count"),
        "warning_step_count": outcome.get("warning_step_count"),
        "physics_gate_passed": outcome.get("physics_gate_passed"),
        "evaluation_compact": outcome.get("evaluation_compact"),
        "constraint_status": constraints.get("constraint_status"),
        "total_mass_kg": constraints.get("total_mass_kg"),
        "total_volume_m3": constraints.get("total_volume_m3"),
        "total_cost_musd": constraints.get("total_cost_musd"),
        "final_eligible": record.get("final_eligible"),
        "final_ineligible_reasons": record.get("final_ineligible_reasons"),
    }


def write_chain_final_answer(chain_dir: Path, answer: Mapping[str, Any]) -> Path:
    path = Path(chain_dir) / CHAIN_FINAL_ANSWER_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(answer, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


__all__ = [
    "CHAIN_FINAL_ANSWER_FILENAME",
    "STATUS_APPROVED",
    "STATUS_NOT_COMPARABLE",
    "STATUS_PROVISIONAL",
    "STATUS_REJECTED",
    "SCORING_BAR_KEYS",
    "collect_chain_candidates",
    "scoring_bar",
    "scoring_bar_drift",
    "select_chain_final_answer",
    "write_chain_final_answer",
]
