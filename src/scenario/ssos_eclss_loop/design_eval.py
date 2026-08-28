"""Scoring and ranking for ECLSS capacity candidates (design doc §9).

Ranking is lexicographic, not a weighted sum: occupants first, then how long
the station sat in a dangerous band, then footprint. A weighted score would let
a few hundred kilograms buy a human life, which is not the trade the objective
states.

    rank_key = (
        not final_eligible,   # eligible candidates first
        -crew_remaining,      # maximise survivors
        critical_step_count,  # minimise time in CRITICAL
        warning_step_count,   # minimise time in WARNING
        total_mass_kg,        # then the cheapest / smallest machine wins
        total_volume_m3,
        total_cost_musd,
    )

``design_penalty`` from :mod:`design_constraints` stays a descriptive number for
reports; it never decides adoption.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

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
    if isinstance(crew_initial, int) and isinstance(crew_remaining, int) and crew_initial > 0:
        outcome["survival_fraction"] = crew_remaining / crew_initial
        outcome["full_survival"] = crew_remaining == crew_initial
    else:
        outcome["survival_fraction"] = None
        outcome["full_survival"] = None
    return outcome


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def candidate_rank_key(record: Mapping[str, Any]) -> tuple:
    """Ascending sort key implementing the lexicographic objective."""
    outcome = record.get("outcome") or {}
    constraints = record.get("constraint_evaluation") or {}
    return (
        not bool(record.get("final_eligible")),
        -_as_int(outcome.get("crew_remaining"), -1),
        _as_int(outcome.get("critical_step_count"), 10**6),
        _as_int(outcome.get("warning_step_count"), 10**6),
        _as_float(constraints.get("total_mass_kg"), float("inf")),
        _as_float(constraints.get("total_volume_m3"), float("inf")),
        _as_float(constraints.get("total_cost_musd"), float("inf")),
    )


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
    require_feasible: bool = True,
    evidence_complete: bool = True,
) -> Dict[str, Any]:
    """Decide whether a candidate may become the final proposal.

    A candidate must be preflight-valid, actually simulated, not worse than
    baseline survival, and — when ``require_feasible`` — inside budget and
    engineering bounds. Missing evidence disqualifies every candidate: the
    Evidence Gate is a property of the review, not of one candidate.
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

    baseline_crew = baseline_outcome.get("crew_remaining")
    crew = outcome.get("crew_remaining")
    if isinstance(baseline_crew, int) and isinstance(crew, int) and crew < baseline_crew:
        reasons.append("worse_than_baseline_survival")

    status = str(constraints.get("constraint_status", ""))
    if require_feasible and status != "feasible":
        reasons.append(f"constraint_status={status or 'unknown'}")

    record["final_eligible"] = not reasons
    record["final_ineligible_reasons"] = reasons
    return record


def select_final_candidate(
    ranked: Sequence[Mapping[str, Any]],
    *,
    baseline_outcome: Mapping[str, Any],
) -> Dict[str, Any]:
    """Pick the final candidate and classify the decision.

    ``approved_final`` requires an eligible candidate that keeps every occupant
    alive. An eligible-but-lossy best candidate, or a best candidate that only
    exists outside the budget, is reported as ``provisional_final`` — useful,
    but not auto-adopted (design doc §9).
    """
    if not ranked:
        return {
            "final_status": STATUS_REJECTED,
            "selected_candidate_id": None,
            "reason": "no candidate was produced",
        }

    best = ranked[0]
    outcome = best.get("outcome") or {}
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
            ),
            "requires_supervisor_approval": True,
        }

    full_survival = (
        isinstance(crew, int) and isinstance(crew_initial, int) and crew == crew_initial
    )
    if not full_survival:
        return {
            "final_status": STATUS_PROVISIONAL,
            "selected_candidate_id": best.get("candidate_id"),
            "reason": (
                f"best feasible candidate keeps {crew}/{crew_initial} occupants alive "
                f"(baseline {baseline_crew}); not full survival"
            ),
            "requires_supervisor_approval": True,
        }

    return {
        "final_status": STATUS_APPROVED,
        "selected_candidate_id": best.get("candidate_id"),
        "reason": (
            f"feasible candidate with full survival ({crew}/{crew_initial}), "
            f"lowest footprint among ranked candidates"
        ),
        "requires_supervisor_approval": False,
    }


__all__ = [
    "STATUS_APPROVED",
    "STATUS_PROVISIONAL",
    "STATUS_REJECTED",
    "band_counts",
    "candidate_rank_key",
    "evaluate_run_outcome",
    "mark_final_eligibility",
    "rank_candidates",
    "read_summary",
    "select_final_candidate",
]
