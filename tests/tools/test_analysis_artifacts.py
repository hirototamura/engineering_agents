"""Unit tests for reading run and chain artifacts into analysis rows.

The fixtures write the smallest run directory the loader accepts, so a schema
change in the artifacts shows up here as a failure rather than as a silently
empty column in the report.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
import yaml

from tools.analysis import artifacts
from tools.analysis.experiments import capacity_proposal

SCENARIO = {
    "plant_sim": {
        "time": {"step_seconds": 1200, "wrs_operation_seconds": 1200},
        "crew": {
            "size": 50, "activity_factor": 1.0,
            "co2_kg_day_person": 1.04, "o2_kg_day_person": 0.84,
            "potable_water_kg_day_person": 2.28,
            "urine_kg_day_person": 1.5, "condensate_kg_day_person": 0.75,
        },
        "ars": {"capacity_kg_day": 4.5},
        "ogs": {"max_o2_kg_day": 9.25},
        "wrs": {"max_feed_l_per_operation": 10.0},
    },
    "thresholds": {"co2_storage_high_kg": 2.0, "o2_storage_low_kg": 6.0,
                   "product_water_low_l": 50.0},
}

AGENTS = {
    "actor": {
        "policy": {
            "ars_goal": {"initial_co2_mass": 4.5},
            "ogs_goal": {"input_water_mass": 0.15},
            "wrs_goal": {"urine_volume": 0.5},
            "request_co2_amount": 0.025,
        }
    }
}


def write_run(
    directory: Path,
    *,
    crew_remaining: int = 0,
    score: float = 23.0,
    tcl_observed: bool = True,
    scenario=None,
    agents=None,
    proposals=None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "summary.json").write_text(json.dumps({
        "scenario": "ssos_eclss_loop", "backend": "plant_sim",
        "actor_mode": "labeled_rule_base", "design_mode": "labeled_rule_base",
        "steps": 4, "seed": 1, "inject_failures": False,
        "crew_initial": 50, "crew_remaining": crew_remaining,
        "crew_lost": 50 - crew_remaining,
        "crew_lost_by_cause": {"co2_warning": 50 - crew_remaining},
        "evaluation_score": score, "evaluation_status": "scored",
        "physics_gate_passed": True,
    }))
    (directory / "evaluation.json").write_text(json.dumps({
        "schema_version": "1.0", "status": "scored",
        "physics_gate": {"passed": True, "checks": [
            {"name": "mass_balance_ledgers", "passed": True,
             "residuals": {"o2_kg": 0.0, "co2_kg": 0.0, "water_l": 1e-12}},
        ]},
        "scores": {"total": score, "max_score": 100, "axes": {
            "tcl": {"status": "scored" if tcl_observed else "right_censored", "score": 1.0,
                    "metrics": {"event_observed": tcl_observed, "tcl_seconds": 3600.0,
                                "survived_through_seconds": 86400.0,
                                "reference_seconds": 57600.0}},
            "environment_trajectory": {"status": "scored", "score": 2.0,
                                       "metrics": {"severity_auc_seconds": 1234.0,
                                                   "mean_normalized_severity": 0.42}},
            "actor_survival": {"status": "scored", "score": 5.0, "metrics": {}},
        }},
    }))
    (directory / "telemetry.jsonl").write_text("\n".join(json.dumps(row) for row in [
        {"step": 0, "co2_storage_kg": 1.0}, {"step": 0, "post_ops": True, "co2_storage_kg": 1.5},
        {"step": 1, "co2_storage_kg": 2.0},
    ]))
    (directory / "health_metrics.jsonl").write_text("\n".join(json.dumps(row) for row in [
        {"step": 0, "overall": "safe"},
        {"step": 0, "post_ops": True, "overall": "warning"},
        {"step": 1, "overall": "critical"},
    ]))
    (directory / "events.jsonl").write_text("\n".join(json.dumps(row) for row in [
        {"step": 0, "kind": "/eclss/events/operational_applied",
         "command": {"kind": "oxygen_generation"},
         "result": {"details": {"fully_satisfied": False, "limited_by": ["ogs_capacity"]}}},
        {"step": 1, "kind": "/eclss/events/operational_applied",
         "command": {"kind": "oxygen_generation"},
         "result": {"details": {"fully_satisfied": True, "limited_by": None}}},
        {"step": 1, "kind": "/eclss/events/operational_applied",
         "command": {"kind": "air_revitalisation"},
         "result": {"details": {"fully_satisfied": True, "limited_by": None}}},
    ]))
    (directory / "scenario_config.yaml").write_text(yaml.safe_dump(scenario or SCENARIO))
    (directory / "agents_config.yaml").write_text(yaml.safe_dump(agents or AGENTS))
    if proposals is not None:
        (directory / "design_proposals.json").write_text(json.dumps(proposals))
    return directory


# --------------------------------------------------------------------------- #
# run record
# --------------------------------------------------------------------------- #
def test_load_run_reads_identity_and_outcome(tmp_path):
    record = artifacts.load_run(write_run(tmp_path / "run"))
    assert record.backend == "plant_sim"
    assert record.crew_remaining == 0
    assert record.survival_fraction == pytest.approx(0.0)
    assert record.full_survival is False


def test_survival_fraction_is_one_when_no_one_is_lost(tmp_path):
    record = artifacts.load_run(write_run(tmp_path / "run", crew_remaining=50))
    assert record.survival_fraction == pytest.approx(1.0)
    assert record.full_survival is True


def test_missing_artifacts_yield_none_rather_than_raising(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    record = artifacts.load_run(empty)
    assert record.crew_remaining is None
    assert record.evaluation_score is None
    assert record.as_row()["run_id"] == "empty"


def test_canonical_telemetry_keeps_one_row_per_step(tmp_path):
    record = artifacts.load_run(write_run(tmp_path / "run"))
    rows = record.telemetry()
    assert [row["step"] for row in rows] == [0, 1]
    assert rows[0]["co2_storage_kg"] == pytest.approx(1.5)  # the post_ops row wins


def test_health_bands_prefer_the_post_ops_row(tmp_path):
    bands = artifacts.load_run(write_run(tmp_path / "run")).band_steps()
    assert bands["warning"] == 1
    assert bands["critical"] == 1
    assert bands["safe"] == 0


def test_mass_balance_residuals_are_read_from_the_physics_gate(tmp_path):
    residuals = artifacts.load_run(write_run(tmp_path / "run")).mass_balance_residuals
    assert residuals["o2_kg"] == pytest.approx(0.0)
    assert residuals["water_l"] == pytest.approx(1e-12)


def test_limiter_rates_separate_capacity_from_other_reasons(tmp_path):
    rates = artifacts.load_run(write_run(tmp_path / "run")).limiter_rates()
    assert rates["oxygen_generation.ogs_capacity"] == pytest.approx(0.5)
    assert rates["oxygen_generation.any"] == pytest.approx(0.5)
    assert "air_revitalisation.any" not in rates


def test_observed_crew_loss_reports_the_event_time(tmp_path):
    seconds, observed = artifacts.load_run(
        write_run(tmp_path / "run")).time_to_crew_loss
    assert observed is True
    assert seconds == pytest.approx(3600.0)


def test_a_run_with_no_crew_loss_is_right_censored_at_the_horizon(tmp_path):
    seconds, observed = artifacts.load_run(
        write_run(tmp_path / "run", tcl_observed=False)).time_to_crew_loss
    assert observed is False
    assert seconds == pytest.approx(86400.0)


def test_coverage_ratios_come_from_the_effective_config(tmp_path):
    scenario = json.loads(json.dumps(SCENARIO))
    scenario["plant_sim"]["ogs"]["max_o2_kg_day"] = 42.0
    record = artifacts.load_run(write_run(tmp_path / "run", scenario=scenario))
    assert record.coverage.ogs == pytest.approx(1.0)


def test_actuation_vector_reads_both_config_files(tmp_path):
    agents = json.loads(json.dumps(AGENTS))
    agents["actor"]["policy"]["ars_goal"]["initial_co2_mass"] = 4.5 * math.e
    record = artifacts.load_run(write_run(tmp_path / "run", agents=agents))
    assert record.actuation_vector["ars_action_co2_mass"] == pytest.approx(1.0)
    assert record.actuation_vector["ars_capacity_kg_day"] == pytest.approx(0.0)


def test_as_row_exposes_the_columns_the_report_needs(tmp_path):
    row = artifacts.load_run(write_run(tmp_path / "run")).as_row()
    for key in ("rho_ars", "rho_ogs", "rho_min", "binding_subsystem",
                "survival_fraction", "evaluation_score", "total_mass_kg",
                "tcl_seconds", "tcl_observed", "residual_o2_kg"):
        assert key in row, key


def test_proposal_change_kinds_are_counted(tmp_path):
    doc = {"design_domain": "ssos_graph", "changes": [
        {"change_kind": "action_profile"}, {"change_kind": "action_profile"},
        {"change_kind": "set_parameter"},
    ]}
    record = artifacts.load_run(write_run(tmp_path / "run", proposals=doc))
    assert record.change_kinds() == {"action_profile": 2, "set_parameter": 1}


# --------------------------------------------------------------------------- #
# chain record
# --------------------------------------------------------------------------- #
def build_chain(root: Path, n: int = 3) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "chain_summary.json").write_text(json.dumps({
        "verdict": "NOT_IMPROVED", "requirements_hash": "abc", "iterations_completed": n,
    }))
    for index in range(1, n + 1):
        agents = json.loads(json.dumps(AGENTS))
        agents["actor"]["policy"]["ars_goal"]["initial_co2_mass"] = 4.5 * (1.25 ** (index - 1))
        run = write_run(root / f"{index:02d}", agents=agents, proposals={
            "changes": [{"change_kind": "action_profile"}, {"change_kind": "set_parameter"}]
        })
        (run / "applied_proposals.json").write_text(json.dumps({
            "changes": [{"change_kind": "action_profile"}]
        }))
    write_run(root / "baseline-replay")
    return root


def test_load_chain_orders_iterations_and_separates_replays(tmp_path):
    chain = artifacts.load_chain(build_chain(tmp_path / "chain"))
    assert len(chain.iterations) == 3
    assert "baseline-replay" in chain.replays
    assert chain.verdict == "NOT_IMPROVED"


def test_applied_changes_exclude_what_the_chain_filtered_out(tmp_path):
    chain = artifacts.load_chain(build_chain(tmp_path / "chain"))
    assert len(chain.iterations[0].proposal_changes()) == 2
    assert len(chain.applied_changes(0)) == 1


def test_chain_rows_carry_the_iteration_index(tmp_path):
    rows = artifacts.load_chain(build_chain(tmp_path / "chain")).as_rows()
    assert [row["iteration"] for row in rows] == [1, 2, 3]
    assert all(row["chain_verdict"] == "NOT_IMPROVED" for row in rows)


def test_chain_dynamics_detects_the_saturating_archetype(tmp_path):
    from tools.analysis.loop_dynamics import analyse_chain

    dynamics = analyse_chain(artifacts.load_chain(build_chain(tmp_path / "chain")))
    assert dynamics.archetype == "saturating"
    assert dynamics.magnitude_share["action"] == pytest.approx(1.0)
    assert dynamics.magnitude_share["capacity"] == pytest.approx(0.0)
    assert dynamics.discarded_fraction == pytest.approx(0.5)


def test_chain_step_norms_are_constant_for_a_fixed_multiplicative_gain(tmp_path):
    from tools.analysis.loop_dynamics import analyse_chain

    dynamics = analyse_chain(artifacts.load_chain(build_chain(tmp_path / "chain", n=4)))
    steps = [state.step_norm for state in dynamics.states[1:]]
    assert steps == pytest.approx([math.log(1.25)] * 3)


def test_turning_cosine_is_one_for_a_straight_march(tmp_path):
    from tools.analysis.loop_dynamics import analyse_chain

    dynamics = analyse_chain(artifacts.load_chain(build_chain(tmp_path / "chain", n=4)))
    turning = [s.turning_cosine for s in dynamics.states if s.turning_cosine is not None]
    assert turning == pytest.approx([1.0] * len(turning))


def test_discover_finds_both_runs_and_chains(tmp_path):
    write_run(tmp_path / "solo")
    build_chain(tmp_path / "chained")
    found = {path.name for path in artifacts.discover(tmp_path)}
    assert found == {"solo", "chained"}


# --------------------------------------------------------------------------- #
# proposal documents
# --------------------------------------------------------------------------- #
def test_capacity_proposal_is_a_valid_single_change_document():
    doc = capacity_proposal({"plant_sim.ogs.max_o2_kg_day": 42.0})
    assert doc["design_domain"] == "ssos_graph"
    assert len(doc["changes"]) == 1
    assert doc["changes"][0]["change_kind"] == "capacity_profile"
    assert doc["changes"][0]["payload"]["fields"]["plant_sim.ogs.max_o2_kg_day"] == 42.0


def test_capacity_proposal_rejects_a_variable_outside_the_design_scope():
    with pytest.raises(ValueError, match="not design variables"):
        capacity_proposal({"plant_sim.ars.capture_efficiency": 0.9})


def test_capacity_proposal_is_accepted_by_the_scenario_validator():
    from scenario.ssos_eclss_loop.design_proposals import apply_design_proposals

    merged = apply_design_proposals(
        json.loads(json.dumps(SCENARIO)),
        capacity_proposal({"plant_sim.ogs.max_o2_kg_day": 42.0}),
        approve_provisional=True,
    )
    assert merged["plant_sim"]["ogs"]["max_o2_kg_day"] == pytest.approx(42.0)
