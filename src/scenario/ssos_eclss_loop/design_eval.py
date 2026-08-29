"""Scoring and ranking for ECLSS capacity candidates (design doc §9).

Full survival is a **hard eligibility condition**, not a ranking key: a design
that loses an occupant cannot be adopted at all, so no amount of saved mass can
buy a human life. Among the designs that keep everyone alive, less time in a
dangerous band beats a lighter machine: a heavy but calm design wins over a
light one that lives in CRITICAL.

    eligible = preflight valid
               and simulated
               and evidence complete
               and crew_remaining == crew_initial      # the clearance line
               and inside the engineering bounds       # you cannot build it otherwise

    rank_key = (
        not final_eligible,   # eligible candidates first
        -crew_remaining,      # only separates the ineligible ones from each other
        critical_step_count,  # among eligible: less CRITICAL dwell first
        warning_step_count,
        total_mass_kg,        # then the smallest machine
        total_volume_m3,
        total_cost_musd,
    )

Budgets are deliberately **not** an eligibility condition (they would leave no
eligible candidate at all at 50 occupants). An eligible candidate that busts a
budget is still selected — as ``provisional_final`` requiring human approval, so
the overage is a decision a person makes rather than a filter that hides the
only surviving design.

``design_penalty`` from :mod:`design_constraints` stays a descriptive number for
reports; it never decides adoption.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from scenario.ssos_eclss_loop.design_constraints import (
    STATUS_FEASIBLE,
    STATUS_OUT_OF_BOUNDS,
    STATUS_OVER_BUDGET,
)

STATUS_APPROVED = "approved_final"
STATUS_PROVISIONAL = "provisional_final"
STATUS_REJECTED = "rejected_final"

_BAND_FIELDS = ("co2_status", "o2_status", "water_status")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def read_summary(run_dir: Path) -> Dict[str, Any]:
    path = Path(run_dir) / "summary.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def band_counts(health_rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Per-step band statistics from ``health_metrics.jsonl``.

    Only the pre-ops row of each step is counted (``post_ops`` rows re-report
    the same step after commands and would double-count dwell time).
    """
    critical = warning = 0
    first_critical: Optional[int] = None
    first_warning: Optional[int] = None
    by_resource: Dict[str, Dict[str, int]] = {
        name: {"warning": 0, "critical": 0} for name in _BAND_FIELDS
    }
    steps = 0
    for row in health_rows:
        if row.get("post_ops"):
            continue
        steps += 1
        overall = str(row.get("overall", "")).lower()
        step = row.get("step")
        if overall == "critical":
            critical += 1
            if first_critical is None and isinstance(step, int):
                first_critical = step
        elif overall == "warning":
            warning += 1
            if first_warning is None and isinstance(step, int):
                first_warning = step
        for name in _BAND_FIELDS:
            status = str(row.get(name, "")).lower()
            if status in ("warning", "critical"):
                by_resource[name][status] += 1
    return {
        "health_step_count": steps,
        "critical_step_count": critical,
        "warning_step_count": warning,
        "first_critical_step": first_critical,
        "first_warning_step": first_warning,
        "band_steps_by_resource": by_resource,
    }


def evaluate_run_outcome(run_dir: Path) -> Dict[str, Any]:
    """Outcome metrics of one completed run directory."""
    run_dir = Path(run_dir)
    summary = read_summary(run_dir)
    health_rows = _read_jsonl(run_dir / "health_metrics.jsonl")
    counts = band_counts(health_rows)

    crew_initial = summary.get("crew_initial")
    crew_remaining = summary.get("crew_remaining")
    outcome: Dict[str, Any] = {
        "run_dir": str(run_dir),
        "steps": summary.get("steps"),
        "backend": summary.get("backend"),
        "actor_mode": summary.get("actor_mode"),
        "design_mode": summary.get("design_mode"),
        "physics_gate_passed": summary.get("physics_gate_passed"),
        "evaluation_status": summary.get("evaluation_status"),
        "evaluation_score": summary.get("evaluation_score"),
        "evaluation_compact": summary.get("evaluation_compact"),
        "crew_initial": crew_initial,
        "crew_remaining": crew_remaining,
        "crew_lost": summary.get("crew_lost"),
        "crew_lost_by_cause": summary.get("crew_lost_by_cause") or {},
        "peak_co2_storage_kg": summary.get("peak_co2_storage_kg"),
        "min_o2_storage_kg": summary.get("min_o2_storage_kg"),
        "final_co2_storage_kg": summary.get("final_co2_storage_kg"),
        "final_o2_storage_kg": summary.get("final_o2_storage_kg"),
        "final_product_water_reserve_l": summary.get("final_product_water_reserve_l"),
        "final_health": summary.get("final_health") or {},
        "operational_command_count": summary.get("operational_command_count"),
        **counts,
    }
    start = occupant_count(crew_initial)
    left = occupant_count(crew_remaining)
    if start is not None and left is not None and start > 0:
        outcome["survival_fraction"] = left / start
        outcome["full_survival"] = left == start
    else:
        outcome["survival_fraction"] = None
        outcome["full_survival"] = None
    return outcome


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def occupant_count(value: Any) -> Optional[int]:
    """An occupant count as ``int``, or None when it is not a whole number.

    ``summary.json`` is JSON, so counts normally arrive as ``int`` — but a
    numpy integer or a float-valued count (``50.0``) is just as correct, and an
    ``isinstance(value, int)`` test would silently make full survival
    unreachable for those. Anything fractional stays None: half an occupant is
    a broken summary, not a survival verdict.
    """
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number != int(number):
        return None
    return int(number)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def evaluation_total(record: Mapping[str, Any]) -> Optional[float]:
    """The candidate's score out of its own applicable maximum, as a percentage.

    Runs can be marked out of 100 or out of 90 depending on whether anyone was
    operating the station, so raw totals from different runs are not comparable.
    The share of what was applicable is.
    """
    compact = (record.get("outcome") or {}).get("evaluation_compact") or {}
    total = compact.get("score")
    maximum = compact.get("max_score")
    if not isinstance(total, (int, float)) or not isinstance(maximum, (int, float)):
        return None
    if float(maximum) <= 0:
        return None
    return 100.0 * float(total) / float(maximum)


def candidate_rank_key(record: Mapping[str, Any]) -> tuple:
    """Ascending sort key: everyone alive, then the scorecard. Nothing else.

    Dwell time, mass, volume and cost used to be separate tie-breaks below
    survival. That let a design win on a handful of calm steps and never have
    its mass compared at all -- one observed run adopted a machine 1210 kg and
    184 MUSD heavier because it spent six fewer steps in the warning band.

    All of those now live inside the score, weighted against each other on one
    sheet, so there is one question after survival: how did this design do?
    """
    outcome = record.get("outcome") or {}
    score = evaluation_total(record)
    return (
        not bool(record.get("final_eligible")),
        # Every eligible candidate keeps the whole crew alive, so this key only
        # orders the ineligible ones among themselves (report readability).
        -_as_int(outcome.get("crew_remaining"), -1),
        # Unscored last: a design whose evaluation could not be produced has not
        # shown anything, and must not outrank one that has.
        -(score if score is not None else -1.0),
    )


RANK_CRITERIA = (
    "final_eligible",
    "crew_remaining",
    "evaluation_score_pct",
)


def _criterion_value(record: Mapping[str, Any], criterion: str) -> Any:
    if criterion == "final_eligible":
        return bool(record.get("final_eligible"))
    if criterion == "evaluation_score_pct":
        score = evaluation_total(record)
        return None if score is None else round(score, 3)
    outcome = record.get("outcome") or {}
    if criterion in outcome:
        return outcome.get(criterion)
    return (record.get("constraint_evaluation") or {}).get(criterion)


def rank_rationale(
    winner: Mapping[str, Any], runner_up: Optional[Mapping[str, Any]]
) -> Dict[str, Any]:
    """Which criterion actually decided the order, and by how much.

    The objective is lexicographic, so the winner is settled by the first
    criterion where two candidates differ, and later criteria are never
    consulted. With survival and the scorecard as the only two criteria there
    is little left to hide, but saying which one decided still tells a reader
    whether a design won on keeping people alive or on the sheet.
    """
    if runner_up is None:
        return {
            "decided_by": None,
            "detail": "only one candidate was simulated",
        }
    for criterion in RANK_CRITERIA:
        left = _criterion_value(winner, criterion)
        right = _criterion_value(runner_up, criterion)
        if left == right:
            continue
        return {
            "decided_by": criterion,
            "winner": winner.get("candidate_id"),
            "winner_value": left,
            "runner_up": runner_up.get("candidate_id"),
            "runner_up_value": right,
            "not_compared": [
                name
                for name in RANK_CRITERIA[RANK_CRITERIA.index(criterion) + 1 :]
                if _criterion_value(winner, name) is not None
            ],
        }
    return {
        "decided_by": None,
        "detail": "candidates are equal on every criterion; original order kept",
    }


def rank_candidates(records: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Sort candidate records best-first and stamp ``rank`` on each."""
    ranked = sorted((dict(r) for r in records), key=candidate_rank_key)
    for index, record in enumerate(ranked, start=1):
        record["rank"] = index
    return ranked


def mark_final_eligibility(
    record: Dict[str, Any],
    *,
    baseline_outcome: Mapping[str, Any],
    require_in_bounds: bool = True,
    require_within_budget: bool = False,
    evidence_complete: bool = True,
) -> Dict[str, Any]:
    """Decide whether a candidate may become the final proposal.

    A candidate must be preflight-valid, actually simulated, keep **every**
    occupant alive, and stay inside the engineering bounds — a machine outside
    those bounds cannot be built, so it is not a design. Missing evidence
    disqualifies every candidate: the Evidence Gate is a property of the
    review, not of one candidate.

    ``require_within_budget`` is off by default: an over-budget design that
    saves the whole crew is a decision for a human (it comes back as
    ``provisional_final``), not something to filter out silently.
    """
    constraints = record.get("constraint_evaluation") or {}
    outcome = record.get("outcome") or {}
    reasons: List[str] = []

    if constraints.get("preflight_status") != "valid":
        reasons.append("preflight_invalid")
    if not record.get("simulated"):
        reasons.append("not_simulated")
    if not evidence_complete:
        reasons.append("evidence_incomplete")

    # The deterministic evaluator is a measurement gate, not a score objective.
    # A plant_sim candidate whose persisted physics cannot be audited is never
    # eligible regardless of survival, mass, or model-written prose.
    if outcome.get("backend") == "plant_sim" and outcome.get("physics_gate_passed") is not True:
        reasons.append("physics_gate_not_passed")

    crew = occupant_count(outcome.get("crew_remaining"))
    crew_initial = occupant_count(outcome.get("crew_initial"))
    if crew is None or crew_initial is None or crew_initial <= 0:
        reasons.append("survival_unknown")
    elif crew < crew_initial:
        reasons.append(f"not_full_survival={crew}/{crew_initial}")

    baseline_crew = occupant_count(baseline_outcome.get("crew_remaining"))
    if baseline_crew is not None and crew is not None and crew < baseline_crew:
        reasons.append("worse_than_baseline_survival")

    status = str(constraints.get("constraint_status", ""))
    if status == STATUS_OUT_OF_BOUNDS and require_in_bounds:
        reasons.append(f"constraint_status={status}")
    elif status == STATUS_OVER_BUDGET and require_within_budget:
        reasons.append(f"constraint_status={status}")
    elif status and status not in (STATUS_FEASIBLE, STATUS_OUT_OF_BOUNDS, STATUS_OVER_BUDGET):
        reasons.append(f"constraint_status={status}")

    record["final_eligible"] = not reasons
    record["final_ineligible_reasons"] = reasons
    return record


def select_final_candidate(
    ranked: Sequence[Mapping[str, Any]],
    *,
    baseline_outcome: Mapping[str, Any],
) -> Dict[str, Any]:
    """Pick the final candidate and classify the decision.

    ``approved_final`` requires an eligible candidate — every occupant alive,
    inside the engineering bounds — that also fits the documented budgets. An
    ineligible best candidate, or an eligible one that busts a budget, is
    reported as ``provisional_final``: useful, but not auto-adopted
    (design doc §9). ``apply_design_proposals`` refuses a provisional document
    unless a human passes ``approve_provisional``.
    """
    if not ranked:
        return {
            "final_status": STATUS_REJECTED,
            "selected_candidate_id": None,
            "reason": "no candidate was produced",
        }

    best = ranked[0]
    outcome = best.get("outcome") or {}
    constraints = best.get("constraint_evaluation") or {}
    baseline_crew = baseline_outcome.get("crew_remaining")
    crew = outcome.get("crew_remaining")
    crew_initial = outcome.get("crew_initial")

    if not best.get("final_eligible"):
        return {
            "final_status": STATUS_PROVISIONAL,
            "selected_candidate_id": best.get("candidate_id"),
            "reason": (
                "best observed candidate is not final-eligible: "
                + ", ".join(best.get("final_ineligible_reasons") or ["unknown"])
                + f" (baseline kept {baseline_crew})"
            ),
            "requires_supervisor_approval": True,
        }

    status = str(constraints.get("constraint_status", ""))
    if status and status != STATUS_FEASIBLE:
        violations = constraints.get("budget_violations") or constraints.get("violations") or []
        return {
            "final_status": STATUS_PROVISIONAL,
            "selected_candidate_id": best.get("candidate_id"),
            "reason": (
                f"smallest design that keeps {crew}/{crew_initial} occupants alive is "
                f"{status}: {'; '.join(str(v) for v in violations) or 'no detail'}"
            ),
            "requires_supervisor_approval": True,
        }

    score = evaluation_total(best)
    score_text = f"{score:.2f}% of the applicable score" if score is not None else "unscored"
    return {
        "final_status": STATUS_APPROVED,
        "selected_candidate_id": best.get("candidate_id"),
        "reason": (
            f"full survival ({crew}/{crew_initial}) and the best scorecard among ranked "
            f"candidates ({score_text}), inside the documented budgets"
        ),
        "requires_supervisor_approval": False,
    }


__all__ = [
    "STATUS_APPROVED",
    "STATUS_PROVISIONAL",
    "STATUS_REJECTED",
    "band_counts",
    "candidate_rank_key",
    "evaluation_total",
    "evaluate_run_outcome",
    "mark_final_eligibility",
    "occupant_count",
    "rank_candidates",
    "read_summary",
    "RANK_CRITERIA",
    "rank_rationale",
    "select_final_candidate",
]
