"""Sizing model, constraint labels and lexicographic ranking (design doc §8, §9)."""

from __future__ import annotations

from dataclasses import replace

import pytest
import yaml

from scenario.runner import scenario_config_path
from scenario.ssos_eclss_loop.design_constraints import (
    STATUS_FEASIBLE,
    STATUS_INVALID,
    STATUS_OUT_OF_BOUNDS,
    STATUS_OVER_BUDGET,
    DesignConstraints,
)
from scenario.ssos_eclss_loop.design_eval import (
    STATUS_APPROVED,
    STATUS_PROVISIONAL,
    band_counts,
    mark_final_eligibility,
    rank_candidates,
    select_final_candidate,
)

BASELINE = {
    "plant_sim.ars.capacity_kg_day": 4.5,
    "plant_sim.ogs.max_o2_kg_day": 9.25,
    "plant_sim.wrs.max_feed_l_per_operation": 10.0,
}


def _constraints() -> DesignConstraints:
    with scenario_config_path("ssos_eclss_loop").open(encoding="utf-8") as f:
        return DesignConstraints.from_scenario_config(yaml.safe_load(f))


def _record(
    candidate_id: str,
    *,
    crew: int,
    critical: int = 0,
    warning: int = 0,
    mass: float = 1800.0,
    volume: float = 6.8,
    cost: float = 259.0,
    status: str = STATUS_FEASIBLE,
    simulated: bool = True,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "simulated": simulated,
        "fields": dict(BASELINE),
        "outcome": {
            "crew_initial": 50,
            "crew_remaining": crew,
            "critical_step_count": critical,
            "warning_step_count": warning,
        },
        "constraint_evaluation": {
            "constraint_status": status,
            "preflight_status": "valid",
            "total_mass_kg": mass,
            "total_volume_m3": volume,
            "total_cost_musd": cost,
        },
    }


def test_baseline_footprint_matches_the_documented_numbers():
    footprint = _constraints().baseline_footprint()
    assert footprint["total_mass_kg"] == pytest.approx(1800.0)
    assert footprint["total_volume_m3"] == pytest.approx(6.8)
    assert footprint["hardware_cost_musd"] == pytest.approx(160.0)
    assert footprint["launch_cost_musd"] == pytest.approx(99.0)
    assert footprint["total_cost_musd"] == pytest.approx(259.0)


def test_capacity_ratio_drives_mass_volume_and_cost():
    constraints = _constraints()
    doubled = constraints.footprint({**BASELINE, "plant_sim.ars.capacity_kg_day": 9.0})
    # ARS mass = 180 fixed + 270 variable × ratio 2
    assert doubled["by_subsystem"]["ars"]["mass_kg"] == pytest.approx(720.0)
    assert doubled["by_subsystem"]["ars"]["capacity_ratio"] == pytest.approx(2.0)


def test_status_labels_bounds_budget_and_schema():
    constraints = _constraints()
    assert constraints.evaluate(BASELINE)["constraint_status"] == STATUS_FEASIBLE
    over = constraints.evaluate({**BASELINE, "plant_sim.ars.capacity_kg_day": 60.0})
    assert over["constraint_status"] == STATUS_OVER_BUDGET
    assert over["simulate_allowed"] is True  # design doc §8.1
    out = constraints.evaluate({**BASELINE, "plant_sim.ars.capacity_kg_day": 800.0})
    assert out["constraint_status"] == STATUS_OUT_OF_BOUNDS
    invalid = constraints.evaluate({"plant_sim.ars.capture_efficiency": 0.99})
    assert invalid["constraint_status"] == STATUS_INVALID
    assert constraints.should_simulate(STATUS_INVALID) is False


def test_a_design_that_loses_an_occupant_is_never_eligible():
    """Full survival is the clearance line, not a ranking key."""
    baseline = {"crew_remaining": 10, "crew_initial": 50}
    lethal = _record("light_but_lethal", crew=49, mass=1800.0)
    safe = _record("heavy_but_safe", crew=50, mass=5000.0, cost=800.0)
    for record in (lethal, safe):
        mark_final_eligibility(record, baseline_outcome=baseline)

    assert lethal["final_eligible"] is False
    assert any(r.startswith("not_full_survival") for r in lethal["final_ineligible_reasons"])
    assert safe["final_eligible"] is True
    ranked = rank_candidates([lethal, safe])
    assert [r["candidate_id"] for r in ranked] == ["heavy_but_safe", "light_but_lethal"]


def test_among_full_survival_designs_the_smallest_wins():
    baseline = {"crew_remaining": 0, "crew_initial": 50}
    records = [
        _record("heavy", crew=50, mass=5000.0),
        _record("light", crew=50, mass=2000.0),
        _record("lighter_but_critical", crew=50, critical=3, mass=1900.0),
    ]
    for record in records:
        mark_final_eligibility(record, baseline_outcome=baseline)
    ranked = rank_candidates(records)
    # Mass decides before dwell time: every candidate here already kept the crew.
    assert [r["candidate_id"] for r in ranked] == ["lighter_but_critical", "light", "heavy"]


def test_dwell_time_only_breaks_a_footprint_tie():
    baseline = {"crew_remaining": 0, "crew_initial": 50}
    calm = _record("calm", crew=50, mass=2000.0)
    tense = _record("tense", crew=50, critical=3, mass=2000.0)
    for record in (calm, tense):
        mark_final_eligibility(record, baseline_outcome=baseline)
    ranked = rank_candidates([tense, calm])
    assert [r["candidate_id"] for r in ranked] == ["calm", "tense"]


def test_over_budget_is_eligible_but_out_of_bounds_is_not():
    """Budgets are money; bounds are what can be built."""
    baseline = {"crew_remaining": 10, "crew_initial": 50}
    over = _record("over_budget", crew=50, status=STATUS_OVER_BUDGET)
    unbuildable = _record("out_of_bounds", crew=50, status=STATUS_OUT_OF_BOUNDS, mass=100.0)
    for record in (over, unbuildable):
        mark_final_eligibility(record, baseline_outcome=baseline)
    assert over["final_eligible"] is True
    assert unbuildable["final_eligible"] is False
    ranked = rank_candidates([unbuildable, over])
    assert ranked[0]["candidate_id"] == "over_budget"


def test_budgets_can_still_be_made_a_hard_gate():
    record = _record("over", crew=50, status=STATUS_OVER_BUDGET)
    mark_final_eligibility(
        record,
        baseline_outcome={"crew_remaining": 0, "crew_initial": 50},
        require_within_budget=True,
    )
    assert record["final_eligible"] is False


def test_candidate_worse_than_baseline_is_not_eligible():
    record = _record("regression", crew=5)
    mark_final_eligibility(
        record, baseline_outcome={"crew_remaining": 20, "crew_initial": 50}
    )
    assert record["final_eligible"] is False
    assert "worse_than_baseline_survival" in record["final_ineligible_reasons"]


def test_a_float_valued_occupant_count_still_reaches_full_survival():
    """A summary that reports 50.0 (or a numpy int) is not a survival failure."""
    record = _record("full", crew=50)
    record["outcome"]["crew_remaining"] = 50.0
    record["outcome"]["crew_initial"] = 50.0
    mark_final_eligibility(record, baseline_outcome={"crew_remaining": 0, "crew_initial": 50})
    assert record["final_eligible"] is True
    selection = select_final_candidate(
        rank_candidates([record]), baseline_outcome={"crew_remaining": 0, "crew_initial": 50}
    )
    assert selection["final_status"] == STATUS_APPROVED


def test_missing_evidence_disqualifies_every_candidate():
    record = _record("fine", crew=50)
    mark_final_eligibility(
        record,
        baseline_outcome={"crew_remaining": 0, "crew_initial": 50},
        evidence_complete=False,
    )
    assert record["final_eligible"] is False
    assert "evidence_incomplete" in record["final_ineligible_reasons"]


def test_full_survival_is_approved_and_partial_survival_is_provisional():
    baseline = {"crew_remaining": 0, "crew_initial": 50}
    full = _record("full", crew=50)
    partial = _record("partial", crew=49)
    for record in (full, partial):
        mark_final_eligibility(record, baseline_outcome=baseline)

    approved = select_final_candidate(rank_candidates([full, partial]), baseline_outcome=baseline)
    assert approved["final_status"] == STATUS_APPROVED
    assert approved["selected_candidate_id"] == "full"

    provisional = select_final_candidate(rank_candidates([partial]), baseline_outcome=baseline)
    assert provisional["final_status"] == STATUS_PROVISIONAL
    assert provisional["requires_supervisor_approval"] is True


def test_over_budget_best_candidate_is_provisional_not_approved():
    """It is still the selected design — a human decides whether to pay for it."""
    baseline = {"crew_remaining": 0, "crew_initial": 50}
    record = _record("over", crew=50, status=STATUS_OVER_BUDGET)
    mark_final_eligibility(record, baseline_outcome=baseline)
    selection = select_final_candidate(rank_candidates([record]), baseline_outcome=baseline)
    assert selection["final_status"] == STATUS_PROVISIONAL
    assert selection["selected_candidate_id"] == "over"
    assert selection["requires_supervisor_approval"] is True


def test_band_counts_ignore_post_ops_rows():
    rows = [
        {"step": 0, "overall": "safe", "co2_status": "safe"},
        {"step": 0, "overall": "critical", "co2_status": "critical", "post_ops": True},
        {"step": 1, "overall": "warning", "co2_status": "warning"},
        {"step": 2, "overall": "critical", "co2_status": "critical"},
    ]
    counts = band_counts(rows)
    assert counts["health_step_count"] == 3
    assert counts["warning_step_count"] == 1
    assert counts["critical_step_count"] == 1
    assert counts["first_critical_step"] == 2


def test_disabled_constraints_report_the_footprint_without_labelling_it():
    """`design_constraints.enabled: false` stops labelling, not measuring."""
    oversized = {
        "plant_sim.ars.capacity_kg_day": 200.0,  # past the 80 kg/day bound
        "plant_sim.ogs.max_o2_kg_day": 200.0,
        "plant_sim.wrs.max_feed_l_per_operation": 10.0,
    }
    enforced = _constraints()
    labelled = enforced.evaluate(oversized)
    assert labelled["constraint_status"] == STATUS_OUT_OF_BOUNDS
    assert labelled["constraints_enforced"] is True

    off = replace(enforced, enabled=False)
    result = off.evaluate(oversized)
    assert result["constraint_status"] == STATUS_FEASIBLE
    assert result["constraints_enforced"] is False
    assert result["violations"] == []
    # the numbers are still there; only the verdict is withheld
    assert result["total_mass_kg"] == pytest.approx(labelled["total_mass_kg"])
    assert off.should_simulate(result["constraint_status"]) is True


def test_disabled_constraints_still_reject_a_variable_outside_the_design_scope():
    off = replace(_constraints(), enabled=False)
    result = off.evaluate({"plant_sim.ogs.recovery_efficiency": 0.9})
    assert result["constraint_status"] == STATUS_INVALID


# --------------------------------------------------------------------------- #
# partial candidates and the installed machine
# --------------------------------------------------------------------------- #
def _constraints_with_installed(**installed) -> DesignConstraints:
    base = _constraints()
    return replace(base, installed_capacity={**base.installed_capacity, **installed})


def test_a_partial_candidate_is_priced_against_the_installed_machine():
    """Naming only ARS does not un-build the OGS a previous review installed."""
    constraints = _constraints_with_installed(ogs=40.0)
    evaluation = constraints.evaluate({"plant_sim.ars.capacity_kg_day": 20.0})
    capacity = evaluation["capacity_by_subsystem"]
    assert capacity["ars"] == 20.0
    assert capacity["ogs"] == 40.0  # installed, not the 9.25 sizing baseline
    assert evaluation["capacity_source"] == {
        "ars": "candidate",
        "ogs": "installed",
        "wrs": "installed",
    }

    naive = _constraints().evaluate({"plant_sim.ars.capacity_kg_day": 20.0})
    assert evaluation["total_mass_kg"] > naive["total_mass_kg"]


def test_the_installed_machine_comes_from_the_scenario_config():
    constraints = DesignConstraints.from_scenario_config(
        {"plant_sim": {"ogs": {"max_o2_kg_day": 37.0}}}
    )
    assert constraints.installed_capacity["ogs"] == 37.0
    assert constraints.installed_capacity["ars"] == BASELINE["plant_sim.ars.capacity_kg_day"]
    # the sizing-model reference point is unchanged by what is installed
    assert constraints.baseline_capacity["ogs"] == 9.25


def test_downsizing_gives_mass_back_relative_to_what_is_installed():
    constraints = _constraints_with_installed(ars=40.0)
    evaluation = constraints.evaluate({"plant_sim.ars.capacity_kg_day": 20.0})
    assert evaluation["delta_installed_mass_kg"] < 0
    assert evaluation["delta_installed_cost_musd"] < 0


# --------------------------------------------------------------------------- #
# objective: config must describe what the code does (§9)
# --------------------------------------------------------------------------- #
def test_an_objective_the_ranking_does_not_implement_is_rejected():
    with pytest.raises(ValueError, match="not implemented"):
        DesignConstraints.from_scenario_config(
            {"design_constraints": {"objective": {"primary": "minimize_cost"}}}
        )


def test_the_shipped_scenario_objective_is_the_implemented_one():
    constraints = _constraints()
    assert constraints.objective_primary == "require_full_survival"
    assert constraints.objective_secondary == "minimize_resource_footprint"
