"""Deterministic design tools over a real baseline run (design doc §5.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scenario.runner import run_scenario
from scenario.ssos_eclss_loop.chain_memory import CHAIN_MEMORY_FILENAME
from scenario.ssos_eclss_loop.design_constraints import DesignConstraints
from scenario.ssos_eclss_loop.design_tools import DesignToolContext, DesignToolkit


def _baseline_run(tmp_path: Path, *, crew: int = 50, steps: int = 12) -> Path:
    return run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "baseline",
        overrides={
            "backend": {"kind": "plant_sim"},
            "simulation": {"steps": steps},
            "plant_sim": {"crew": {"size": crew}},
            "agents": {
                "actor": {"mode": "labeled_rule_base", "team": {"count": crew}},
                "design": {"mode": "none"},
            },
        },
        recreate_output=True,
    )


def _toolkit(run_dir: Path, **ctx_kwargs) -> DesignToolkit:
    scenario_config = yaml.safe_load((run_dir / "scenario_config.yaml").read_text(encoding="utf-8"))
    agents_config = yaml.safe_load((run_dir / "agents_config.yaml").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    kwargs = {
        "max_candidate_runs": 2,
        "plots_enabled": False,
        "candidate_steps": 12,
        **ctx_kwargs,
    }
    return DesignToolkit(
        DesignToolContext(
            run_dir=run_dir,
            scenario_config=scenario_config,
            summary=summary,
            agents_config=agents_config,
            constraints=DesignConstraints.from_scenario_config(scenario_config),
            **kwargs,
        )
    )


@pytest.fixture(scope="module")
def baseline(tmp_path_factory) -> Path:
    return _baseline_run(tmp_path_factory.mktemp("design_tools"))


def test_catalog_matches_the_design_document(baseline: Path):
    names = _toolkit(baseline).tool_names()
    assert names == [
        "load_run_artifacts",
        "summarize_timeseries",
        "compute_eclss_features",
        "compute_theoretical_capacity",
        "plot_eclss_timeseries",
        "propose_capacity_candidate",
        "evaluate_design_constraints",
        "run_design_candidate",
        "compare_design_runs",
    ]


def test_unknown_tool_and_bad_arguments_come_back_as_errors(baseline: Path):
    toolkit = _toolkit(baseline)
    assert "error" in toolkit.call("no_such_tool", {})
    assert "error" in toolkit.call("summarize_timeseries", {"source": "nope"})
    assert "error" in toolkit.call("evaluate_design_constraints", {})
    # a failed call must not count as evidence
    assert toolkit.evidence.get("evaluated_constraints") is not True


def test_load_run_artifacts_reports_every_stream(baseline: Path):
    toolkit = _toolkit(baseline)
    result = toolkit.call("load_run_artifacts", {})
    assert result["telemetry"]["row_count"] > 0
    assert result["health_metrics"]["row_count"] > 0
    assert result["scenario_config"]["plant_sim"]["crew"]["size"] == 50
    assert toolkit.evidence["read_baseline_artifacts"] is True


def test_a_run_outside_a_chain_reports_no_chain_memory(baseline: Path):
    """The first iteration, and every standalone run, has no earlier round."""
    assert _toolkit(baseline).call("load_run_artifacts", {})["chain_memory_compact"] is None


def test_the_artifacts_carry_what_earlier_iterations_of_the_chain_left(baseline: Path):
    """The note lives at the chain root, one level above the iteration."""
    chain_dir = baseline.parent
    note = chain_dir / CHAIN_MEMORY_FILENAME
    note.write_text(
        json.dumps({"schema_version": "1.0", "best_full_survival": {"iteration": 4}}),
        encoding="utf-8",
    )
    try:
        memory = _toolkit(baseline).call("load_run_artifacts", {})["chain_memory_compact"]
        assert memory["best_full_survival"]["iteration"] == 4
    finally:
        note.unlink()


def test_an_unreadable_chain_memory_does_not_break_the_design_loop(baseline: Path):
    """A corrupt note is a reason to design without one, not to stop designing."""
    note = baseline.parent / CHAIN_MEMORY_FILENAME
    note.write_text("{ truncated", encoding="utf-8")
    try:
        result = _toolkit(baseline).call("load_run_artifacts", {})
        assert result["chain_memory_compact"]["error"] == "failed_to_load_chain_memory"
        # the rest of the artifacts still came back, and the tool still counts
        assert result["telemetry"]["row_count"] > 0
        assert result.get("error") is None
    finally:
        note.unlink()


def test_summarize_timeseries_finds_the_co2_band_crossings(baseline: Path):
    toolkit = _toolkit(baseline)
    result = toolkit.call(
        "summarize_timeseries", {"source": "telemetry", "columns": ["co2_storage_kg"]}
    )
    co2 = result["columns"]["co2_storage_kg"]
    assert co2["n"] > 0
    assert co2["max"] >= co2["min"]
    # 50 occupants against a 4.5 kg/day ARS: CO2 climbs past the warning band
    assert co2["steps_in_warning"] + co2["steps_in_critical"] > 0
    assert co2["warning_threshold"] == pytest.approx(2.0)


def test_health_source_returns_band_dwell(baseline: Path):
    result = _toolkit(baseline).call("summarize_timeseries", {"source": "health_metrics"})
    assert result["health_step_count"] > 0
    assert result["critical_step_count"] + result["warning_step_count"] > 0


def test_features_expose_commands_rejections_and_loss_causes(baseline: Path):
    features = _toolkit(baseline).call("compute_eclss_features", {})
    assert features["commands_applied"].get("air_revitalisation", 0) > 0
    # the busy guard is visible to the designer as rejected ARS commands
    rejections = features["commands_rejected_by_reason"]
    assert rejections.get("subsystem_busy", 0) > 0
    assert "ars" in features["subsystem_stress"]
    assert features["outcome"]["crew_initial"] == 50


def test_theoretical_capacity_detects_the_ars_and_ogs_shortfall(baseline: Path):
    theory = _toolkit(baseline).call("compute_theoretical_capacity", {})
    assert theory["crew_size"] == 50
    assert theory["crew_demand_per_day"]["co2_generated_kg_day"] == pytest.approx(52.0)
    assert theory["crew_demand_per_day"]["o2_demand_kg_day"] == pytest.approx(42.0)

    ars = theory["subsystems"]["ars"]
    assert ars["busy_steps"] == 4  # 4800 s operation / 1200 s step
    assert ars["max_actions_per_day"] == 18
    assert ars["shortfall_kg_day"] > 0
    assert ars["coverage_ratio"] < 1.0

    ogs = theory["subsystems"]["ogs"]
    assert ogs["busy_steps"] == 1
    assert ogs["shortfall_kg_day"] > 0
    # WRS is already large enough for 50 occupants (design doc §3)
    assert theory["subsystems"]["wrs"]["coverage_ratio"] > 1.0


def test_theoretical_capacity_reports_request_limited_ogs(baseline: Path):
    theory = _toolkit(baseline).call(
        "compute_theoretical_capacity", {"fields": {"plant_sim.ogs.max_o2_kg_day": 60.0}}
    )
    ogs = theory["subsystems"]["ogs"]
    # nameplate raised but ogs_goal.input_water_mass still small → request limited
    assert ogs["request_limited"] is True
    assert ogs["input_water_mass_for_nameplate_kg"] > ogs["input_water_mass_now_kg"]


def test_propose_capacity_candidate_sizes_from_theory(baseline: Path):
    candidate = _toolkit(baseline).call("propose_capacity_candidate", {"margin": 1.15})
    fields = candidate["fields"]
    assert set(fields) == {
        "plant_sim.ars.capacity_kg_day",
        "plant_sim.ogs.max_o2_kg_day",
        "plant_sim.wrs.max_feed_l_per_operation",
    }
    assert fields["plant_sim.ars.capacity_kg_day"] > 4.5
    assert fields["plant_sim.ogs.max_o2_kg_day"] > 9.25
    assert "constraint_status" in candidate["constraint_preview"]


def test_invalid_candidate_is_never_simulated(baseline: Path):
    toolkit = _toolkit(baseline)
    result = toolkit.call(
        "run_design_candidate", {"fields": {"plant_sim.ars.capture_efficiency": 0.99}}
    )
    assert result["simulated"] is False
    assert result["constraint_evaluation"]["constraint_status"] == "invalid"
    assert "run_dir" not in result  # no simulation directory was created for it
    assert result["error"].startswith("candidate not simulated")


def test_candidate_run_disables_post_run_design_and_improves_survival(baseline: Path):
    toolkit = _toolkit(baseline)
    fields = toolkit.call("propose_capacity_candidate", {"margin": 1.2})["fields"]
    result = toolkit.call("run_design_candidate", {"fields": fields, "label": "sized"})
    assert result["simulated"] is True

    candidate_dir = Path(result["run_dir"])
    candidate_summary = json.loads((candidate_dir / "summary.json").read_text(encoding="utf-8"))
    assert candidate_summary["design_mode"] == "none"  # design doc §12
    assert not (candidate_dir / "design_proposals.json").exists()
    assert result["outcome"]["crew_remaining"] >= result["baseline_outcome"]["crew_remaining"]
    # the capacity change reached the candidate's own effective config
    candidate_config = yaml.safe_load(
        (candidate_dir / "scenario_config.yaml").read_text(encoding="utf-8")
    )
    assert candidate_config["plant_sim"]["ars"]["capacity_kg_day"] == pytest.approx(
        fields["plant_sim.ars.capacity_kg_day"]
    )


def test_candidate_budget_is_enforced(baseline: Path):
    toolkit = _toolkit(baseline, max_candidate_runs=1)
    fields = {"plant_sim.ars.capacity_kg_day": 20.0}
    assert toolkit.call("run_design_candidate", {"fields": fields})["simulated"] is True
    exhausted = toolkit.call("run_design_candidate", {"fields": fields})
    assert "candidate budget exhausted" in exhausted["error"]


def test_compare_requires_a_simulated_candidate_then_ranks(baseline: Path):
    toolkit = _toolkit(baseline)
    assert "error" in toolkit.call("compare_design_runs", {})

    toolkit.call("run_design_candidate", {"fields": {"plant_sim.ars.capacity_kg_day": 25.0}})
    comparison = toolkit.call("compare_design_runs", {})
    assert comparison["ranking"][0]["rank"] == 1
    assert comparison["selection"]["final_status"] in {
        "approved_final",
        "provisional_final",
        "rejected_final",
    }
    assert "crew_remaining" in comparison["baseline"]


def test_evidence_ledger_tracks_what_the_gate_requires(baseline: Path):
    toolkit = _toolkit(baseline)
    assert toolkit.evidence_complete() is False
    toolkit.call("load_run_artifacts", {})
    toolkit.call("summarize_timeseries", {"source": "telemetry"})
    toolkit.call("compute_theoretical_capacity", {})
    fields = toolkit.call("propose_capacity_candidate", {"margin": 1.2})["fields"]
    toolkit.call("evaluate_design_constraints", {"fields": fields})
    assert toolkit.evidence_complete() is False  # no candidate run yet
    toolkit.call("run_design_candidate", {"fields": fields})
    toolkit.call("compare_design_runs", {})
    assert toolkit.missing_evidence() == []


def test_plot_writes_a_png_with_the_same_numbers(baseline: Path, tmp_path: Path):
    toolkit = _toolkit(baseline, plots_enabled=True)
    result = toolkit.call(
        "plot_eclss_timeseries",
        {"columns": ["co2_storage_kg", "o2_storage_kg", "ars_failure_enabled"]},
    )
    if result.get("plot_error"):  # matplotlib backend unavailable on this host
        pytest.skip(result["plot_error"])
    plot_path = Path(result["plot_path"])
    assert plot_path.exists() and plot_path.stat().st_size > 0
    # image understanding is never required: the features come back as numbers
    assert result["columns"]["co2_storage_kg"]["max"] > 0
    # boolean failure flags are series too (0 / 1)
    assert result["columns"]["ars_failure_enabled"]["max"] in (0.0, 1.0)
    assert toolkit.plot_paths == [str(plot_path)]


def test_a_single_column_name_is_read_as_one_column(baseline: Path):
    """A model that means one column writes the bare string, not a list."""
    toolkit = _toolkit(baseline)
    result = toolkit.call("summarize_timeseries", {"columns": "co2_storage_kg"})
    # not list("co2_storage_kg") -> fourteen one-character columns
    assert list(result["columns"]) == ["co2_storage_kg"]
    assert result["columns"]["co2_storage_kg"]["n"] > 0
    assert toolkit.call("load_run_artifacts", {"files": "summary"})["summary"]
    single = toolkit.call("propose_capacity_candidate", {"subsystems": "ars"})
    assert list(single["fields"]) == ["plant_sim.ars.capacity_kg_day"]


def test_a_list_argument_of_the_wrong_type_is_a_visible_error(baseline: Path):
    result = _toolkit(baseline).call("summarize_timeseries", {"columns": {"a": 1}})
    assert "columns must be a list of names" in result["error"]


def test_housekeeping_calls_do_not_credit_the_evidence_ledger(baseline: Path):
    """Report assembly re-ranks candidates; the ledger records the designer only."""
    toolkit = _toolkit(baseline)
    fields = {"plant_sim.ars.capacity_kg_day": 24.0}
    toolkit.call("run_design_candidate", {"fields": fields})
    toolkit.call("compare_design_runs", {}, record_evidence=False)
    assert toolkit.evidence.get("compared_runs") is not True
    assert "compared_runs" in toolkit.missing_evidence()
    toolkit.call("compare_design_runs", {})
    assert toolkit.evidence["compared_runs"] is True


# --------------------------------------------------------------------------- #
# sizing follows demand in both directions (review finding 5)
# --------------------------------------------------------------------------- #
def test_the_sizing_helper_can_shrink_an_oversized_subsystem(baseline: Path):
    """Spare capacity is mass, volume and cost — sizing down is a design move."""
    scenario_config = yaml.safe_load(
        (baseline / "scenario_config.yaml").read_text(encoding="utf-8")
    )
    oversized = json.loads(json.dumps(scenario_config))
    oversized["plant_sim"]["ars"]["capacity_kg_day"] = 300.0
    oversized["plant_sim"]["ogs"]["max_o2_kg_day"] = 300.0
    oversized["plant_sim"]["wrs"]["max_feed_l_per_operation"] = 19.0
    toolkit = DesignToolkit(
        DesignToolContext(
            run_dir=baseline,
            scenario_config=oversized,
            summary=json.loads((baseline / "summary.json").read_text(encoding="utf-8")),
            agents_config=yaml.safe_load(
                (baseline / "agents_config.yaml").read_text(encoding="utf-8")
            ),
            constraints=DesignConstraints.from_scenario_config(oversized),
            max_candidate_runs=1,
            plots_enabled=False,
            candidate_steps=12,
        )
    )

    candidate = toolkit.call("propose_capacity_candidate", {"margin": 1.15})
    fields = candidate["fields"]
    assert fields["plant_sim.ars.capacity_kg_day"] < 300.0
    assert fields["plant_sim.ogs.max_o2_kg_day"] < 300.0


def test_sizing_never_leaves_the_buildable_range(baseline: Path):
    toolkit = _toolkit(baseline)
    bounds = toolkit.constraints.bounds
    candidate = toolkit.call("propose_capacity_candidate", {"margin": 0.001})
    fields = candidate["fields"]
    assert fields["plant_sim.ars.capacity_kg_day"] >= bounds["ars"]["min"]
    assert fields["plant_sim.ogs.max_o2_kg_day"] >= bounds["ogs"]["min"]
    assert fields["plant_sim.wrs.max_feed_l_per_operation"] >= bounds["wrs"]["min"]


# --------------------------------------------------------------------------- #
# the comparison tool grades nothing on the model's word (review finding 4)
# --------------------------------------------------------------------------- #
def test_the_model_cannot_declare_its_own_evidence_complete(baseline: Path):
    toolkit = _toolkit(baseline)
    spec = next(row for row in toolkit.catalog() if row["name"] == "compare_design_runs")
    assert spec["arguments"] == {}

    result = toolkit.call("compare_design_runs", {"evidence_complete": True})
    assert result["error"].startswith("bad arguments for compare_design_runs")


def test_the_first_comparison_does_not_report_a_lying_ranking(baseline: Path):
    """`compared_runs` is credited by this very call; it must not judge itself missing."""
    toolkit = _toolkit(baseline)
    for name, arguments in (
        ("load_run_artifacts", {}),
        ("summarize_timeseries", {"source": "telemetry"}),
        ("compute_theoretical_capacity", {}),
        ("evaluate_design_constraints", {"fields": {"plant_sim.ars.capacity_kg_day": 40.0}}),
        ("run_design_candidate", {"fields": {"plant_sim.ars.capacity_kg_day": 40.0}}),
    ):
        assert "error" not in toolkit.call(name, arguments)

    first = toolkit.call("compare_design_runs", {})
    assert first["evidence_complete"] is True
    assert all(
        "evidence_incomplete" not in (row["final_ineligible_reasons"] or [])
        for row in first["ranking"]
    )
