"""Deterministic scorecard tests for ssos_eclss_loop."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scenario.runner import run_scenario
from scenario.ssos_eclss_loop.evaluation import (
    _resource_recovery_axis,
    _tcl_axis,
    evaluate_run,
    select_telemetry_rows,
)


def _config() -> dict:
    path = (
        Path(__file__).parents[2]
        / "src"
        / "scenario"
        / "ssos_eclss_loop"
        / "scenario.yaml"
    )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_select_telemetry_rows_prefers_post_ops_and_preserves_pre():
    rows = [
        {"step": 0, "co2_storage_kg": 1.0},
        {"step": 1, "co2_storage_kg": 2.0},
        {"step": 1, "post_ops": True, "co2_storage_kg": 1.5},
    ]
    canonical, pre = select_telemetry_rows(rows)
    assert [row["co2_storage_kg"] for row in canonical] == [1.0, 1.5]
    assert pre[1]["co2_storage_kg"] == 2.0


def test_tcl_scores_observed_event_and_right_censors_short_run():
    config = {"tcl": {"reference_seconds": 100.0}}
    rows = [
        {"step": 0, "raw_topics": {"plant_sim": {"simulation_time_s": 0.0}}},
        {"step": 1, "raw_topics": {"plant_sim": {"simulation_time_s": 50.0}}},
    ]
    observed = _tcl_axis(
        rows,
        [
            {
                "step": 1,
                "kind": "/eclss/events/crew_lost",
                "crew_lost_by_cause": {"o2_physics": 1},
            }
        ],
        config,
        50.0,
    )
    assert observed["status"] == "scored"
    assert observed["score"] == pytest.approx(5.0)
    assert observed["metrics"]["tcl_causes"] == {"o2_physics": 1}

    censored = _tcl_axis(rows, [], config, 50.0)
    assert censored["status"] == "right_censored"
    assert censored["score"] is None


def test_resource_recovery_uses_actor_pre_event_values():
    thresholds = {
        "co2_storage_high_kg": 2.0,
        "co2_storage_critical_kg": 8.0,
        "o2_storage_low_kg": 6.0,
        "o2_storage_critical_kg": 1.0,
        "product_water_low_l": 50.0,
        "product_water_critical_l": 25.0,
    }
    rows = [
        {
            "step": 0,
            "co2_storage_kg": 1.0,
            "o2_storage_kg": 8.0,
            "product_water_reserve_l": 80.0,
        },
        {
            "step": 1,
            "co2_storage_kg": 3.0,
            "o2_storage_kg": 5.0,
            "product_water_reserve_l": 45.0,
        },
        {
            "step": 2,
            "co2_storage_kg": 1.5,
            "o2_storage_kg": 7.0,
            "product_water_reserve_l": 60.0,
        },
    ]
    event = {"step": 1, "kind": "subsystem_failure_applied", "enabled": True, "subsystem": "ars"}
    axis = _resource_recovery_axis(
        rows,
        {0: rows[0], 1: rows[1], 2: rows[2]},
        [event],
        thresholds,
        {
            "resource_recovery": {
                "resource_weights": {"co2": 1, "o2": 1, "water": 1},
                "terminal_weight": 0.5,
            }
        },
    )
    resources = axis["metrics"]["resources"]
    assert resources["co2"]["initial"] == pytest.approx(1.0)
    assert resources["co2"]["event"] == pytest.approx(3.0)
    assert resources["co2"]["event_minus_initial"] == pytest.approx(2.0)
    assert resources["o2"]["event"] == pytest.approx(5.0)
    assert resources["water"]["event"] == pytest.approx(45.0)


def test_plant_run_writes_scored_evaluation_and_summary_index(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "plant_eval",
        overrides={
            "backend": {"kind": "plant_sim"},
            "simulation": {"steps": 50},
            "agents": {"actor": {"mode": "none"}, "design": {"mode": "none"}},
        },
        recreate_output=True,
    )
    evaluation = _read_json(run_dir / "evaluation.json")
    summary = _read_json(run_dir / "summary.json")

    assert evaluation["status"] == "scored"
    assert evaluation["physics_gate"]["passed"] is True
    # 90 with nobody operating: every axis but the two operating ones.
    assert evaluation["scores"]["max_score"] == 90
    axes = evaluation["scores"]["axes"]
    # Cost and mass are marked here, not compared separately below survival.
    assert axes["cost"]["max_score"] == 20
    assert axes["mass"]["max_score"] == 20
    assert axes["actor_survival"]["max_score"] == 20
    assert "actor_decision" not in evaluation["scores"]["axes"]
    assert "physical_response" not in evaluation["scores"]["axes"]
    assert summary["evaluation_path"] == str(run_dir / "evaluation.json")
    assert summary["evaluation_html_path"] == str(run_dir / "evaluation.html")
    assert summary["evaluation_status"] == evaluation["status"]
    assert summary["evaluation_score"] == evaluation["scores"]["total"]
    assert summary["physics_gate_passed"] is True
    html = (run_dir / "evaluation.html").read_text(encoding="utf-8")
    assert "ECLSSシミュレーション 評価結果" in html
    assert "物理整合性ゲート" in html
    assert "シミュレーション条件" in html
    assert "inject_failures" in html
    assert evaluation["run_conditions"]["run_id"] == run_dir.name
    assert evaluation["run_conditions"]["backend"] == "plant_sim"
    assert evaluation["run_conditions"]["steps"] == 50
    assert evaluation["run_conditions"]["inject_failures"] is False
    assert evaluation["run_conditions"]["actor"]["mode"] == "none"
    browser = (run_dir.parent / "evaluation.html").read_text(encoding="utf-8")
    assert "ECLSS 評価ブラウザ" in browser
    assert run_dir.name in browser
    assert "別 run と比較" in browser
    assert "../evaluation.html" in html


def test_evaluation_browser_lists_multiple_runs_and_compare_controls(tmp_path: Path):
    from scenario.ssos_eclss_loop.evaluation_browser import write_evaluation_browser

    for run_id, total in (("e001", 40.0), ("e002", 55.0)):
        run_dir = tmp_path / run_id
        run_dir.mkdir()
        (run_dir / "evaluation.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "scenario": "ssos_eclss_loop",
                    "status": "scored",
                    "run_conditions": {
                        "run_id": run_id,
                        "backend": "plant_sim",
                        "steps": 50,
                        "inject_failures": True,
                        "actor": {"mode": "labeled_rule_base", "llm_active": False},
                        "design": {
                            "mode": "llm",
                            "llm_active": True,
                            "provider": "vllm",
                            "model": "qwen3.8-27b-uncensored",
                        },
                    },
                    "physics_gate": {"passed": True, "checks": []},
                    "scores": {
                        "total": total,
                        "max_score": 100,
                        "axes": {
                            "actor_survival": {"score": total / 2, "max_score": 50},
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    path = write_evaluation_browser(tmp_path, default_run_id="e002")
    html = path.read_text(encoding="utf-8")
    assert path.name == "evaluation.html"
    assert "e001" in html and "e002" in html
    assert "qwen3.8-27b-uncensored" in html
    assert "compare-enabled" in html
    assert '"e002"' in html


def test_mock_run_writes_not_applicable_evaluation(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "mock_eval",
        overrides={
            "backend": {"kind": "mock"},
            "simulation": {"steps": 2},
            "agents": {"actor": {"mode": "none"}, "design": {"mode": "none"}},
        },
        recreate_output=True,
    )
    evaluation = _read_json(run_dir / "evaluation.json")
    assert evaluation["status"] == "not_applicable"
    assert evaluation["applicability"]["reason"] == "plant_sim_required"
    html = (run_dir / "evaluation.html").read_text(encoding="utf-8")
    assert "適用対象外" in html


def test_actor_run_scores_decision_and_physical_response(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "actor_eval",
        overrides={
            "backend": {"kind": "plant_sim"},
            "simulation": {"steps": 20},
            "agents": {
                "actor": {"mode": "labeled_rule_base"},
                "design": {"mode": "none"},
            },
        },
        recreate_output=True,
    )
    evaluation = _read_json(run_dir / "evaluation.json")
    axes = evaluation["scores"]["axes"]
    assert evaluation["scores"]["max_score"] == 100
    assert axes["actor_decision"]["status"] == "scored"
    assert axes["physical_response"]["status"] == "scored"
    assert axes["physical_response"]["metrics"]["valid_operation_count"] > 0


def test_non_finite_telemetry_invalidates_physics_gate(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "invalid_eval",
        overrides={
            "backend": {"kind": "plant_sim"},
            "simulation": {"steps": 3},
            "agents": {"actor": {"mode": "none"}, "design": {"mode": "none"}},
            "evaluation": {"tcl": {"reference_seconds": 1}},
        },
        recreate_output=True,
    )
    telemetry_path = run_dir / "telemetry.jsonl"
    rows = [
        json.loads(line)
        for line in telemetry_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows[0]["co2_storage_kg"] = None
    telemetry_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    summary = _read_json(run_dir / "summary.json")
    evaluation = evaluate_run(run_dir, scenario_config=_config(), summary=summary)
    assert evaluation["status"] == "invalid"
    assert evaluation["physics_gate"]["passed"] is False


# --------------------------------------------------------------------------- #
# the scorecard: what a design costs is marked, not compared separately
# --------------------------------------------------------------------------- #
def test_the_sheet_adds_up_to_what_it_claims():
    from scenario.ssos_eclss_loop import evaluation as ev

    performance = ev.TCL_MAX + ev.TRAJECTORY_MAX + ev.RECOVERY_MAX
    assert performance + ev.CREW_MAX + ev.COST_MAX + ev.MASS_MAX == ev.NO_ACTOR_MAX
    assert (
        performance + ev.CREW_MAX + ev.COST_MAX + ev.MASS_MAX + ev.DECISION_MAX + ev.RESPONSE_MAX
        == ev.FULL_MAX
    )


def _capacity_config(ars: float, ogs: float, wrs: float) -> dict:
    import yaml

    from scenario.runner import scenario_config_path

    config = yaml.safe_load(scenario_config_path("ssos_eclss_loop").read_text(encoding="utf-8"))
    config["plant_sim"]["ars"]["capacity_kg_day"] = ars
    config["plant_sim"]["ogs"]["max_o2_kg_day"] = ogs
    config["plant_sim"]["wrs"]["max_feed_l_per_operation"] = wrs
    return config


def test_the_baseline_machine_scores_full_marks_on_what_it_costs():
    """Full marks at the machine the station already has, not below it.

    The baseline is the reference point, not a target to undercut: a design
    cannot earn credit for being smaller than the thing being replaced.
    """
    from scenario.ssos_eclss_loop.evaluation import COST_MAX, MASS_MAX, _footprint_axis

    config = _capacity_config(4.5, 9.25, 10.0)
    cost = _footprint_axis(config, quantity="total_cost_musd", max_score=COST_MAX, zero_at=750.0)
    mass = _footprint_axis(config, quantity="total_mass_kg", max_score=MASS_MAX, zero_at=5000.0)
    assert cost["score"] == COST_MAX
    assert mass["score"] == MASS_MAX
    # The sizing model's baseline is the scorecard's reference: 1800 kg / 259 MUSD.
    assert round(mass["metrics"]["baseline_value"]) == 1800
    assert round(cost["metrics"]["baseline_value"]) == 259


def test_a_bigger_machine_gives_up_marks_for_being_bigger():
    from scenario.ssos_eclss_loop.evaluation import MASS_MAX, _footprint_axis

    small = _footprint_axis(
        _capacity_config(25.0, 50.0, 10.0),
        quantity="total_mass_kg",
        max_score=MASS_MAX,
        zero_at=5000.0,
    )
    large = _footprint_axis(
        _capacity_config(80.0, 80.0, 20.0),
        quantity="total_mass_kg",
        max_score=MASS_MAX,
        zero_at=5000.0,
    )
    assert large["score"] <= small["score"]
    # Past the zero point the axis stops, it does not go negative and eat the
    # rest of the sheet.
    assert large["score"] == 0.0


def test_full_marks_move_to_the_configured_line_not_the_baseline():
    """Marking against a machine that kills everyone cannot rank the survivors.

    The baseline loses all fifty occupants, so every design that keeps them
    alive is larger than it and all of them scored near the floor. Two very
    different survivable designs came out at 11.57 and 4.08 out of 40 — the
    sheet could not tell a lean machine from a bloated one.
    """
    from scenario.ssos_eclss_loop.evaluation import COST_MAX, MASS_MAX, _footprint_axis

    config = _capacity_config(20.8, 42.0, 2.0)
    # At or under the line is full marks, whatever the baseline was.
    under_line = _footprint_axis(
        config, quantity="total_cost_musd", max_score=COST_MAX, zero_at=900.0, full_at=700.0
    )
    assert under_line["score"] == COST_MAX

    cost = _footprint_axis(
        config, quantity="total_cost_musd", max_score=COST_MAX, zero_at=900.0, full_at=500.0
    )
    mass = _footprint_axis(
        config, quantity="total_mass_kg", max_score=MASS_MAX, zero_at=6000.0, full_at=3400.0
    )
    # The design that kept 50 of 50 on the smallest machine observed: E ~ 29/40,
    # room above it and room below.
    assert 28.0 < cost["score"] + mass["score"] < 32.0
    assert cost["metrics"]["full_score_value"] == 500.0
    assert cost["metrics"]["zero_score_value"] == 900.0
    assert cost["metrics"]["over_full_score_value"] == pytest.approx(
        cost["metrics"]["value"] - 500.0
    )
    assert 0.0 < cost["metrics"]["fraction_of_headroom_used"] < 1.0
    # The shipped machine is still named, it is just no longer where full marks sit.
    assert round(cost["metrics"]["baseline_value"]) == 259


def test_an_oversized_survivor_scores_clearly_below_a_lean_one():
    from scenario.ssos_eclss_loop.evaluation import COST_MAX, MASS_MAX, _footprint_axis

    def footprint_score(ars: float, ogs: float, wrs: float) -> float:
        config = _capacity_config(ars, ogs, wrs)
        cost = _footprint_axis(
            config, quantity="total_cost_musd", max_score=COST_MAX, zero_at=900.0, full_at=500.0
        )
        mass = _footprint_axis(
            config, quantity="total_mass_kg", max_score=MASS_MAX, zero_at=6000.0, full_at=3400.0
        )
        return cost["score"] + mass["score"]

    lean = footprint_score(20.8, 42.0, 2.0)
    bloated = footprint_score(23.92, 48.3, 5.0)
    # Both keep every occupant alive. Before the line moved these sat at 11.57
    # and 4.08; what matters is that the gap is now readable either way.
    assert lean - bloated > 5.0


def test_omitting_the_full_score_line_keeps_the_old_baseline_behaviour():
    from scenario.ssos_eclss_loop.evaluation import MASS_MAX, _footprint_axis

    config = _capacity_config(20.8, 42.0, 2.0)
    without = _footprint_axis(
        config, quantity="total_mass_kg", max_score=MASS_MAX, zero_at=5000.0
    )
    explicit = _footprint_axis(
        config, quantity="total_mass_kg", max_score=MASS_MAX, zero_at=5000.0, full_at=1800.0
    )
    assert without["score"] == explicit["score"]
    assert without["metrics"]["full_score_value"] == pytest.approx(1800.0)


def test_a_zero_line_at_or_under_the_full_line_is_not_scored():
    """Everything would be worth all the marks or none; the sheet says so."""
    from scenario.ssos_eclss_loop.evaluation import MASS_MAX, _footprint_axis

    for zero_at in (3400.0, 3000.0):
        axis = _footprint_axis(
            _capacity_config(20.8, 42.0, 2.0),
            quantity="total_mass_kg",
            max_score=MASS_MAX,
            zero_at=zero_at,
            full_at=3400.0,
        )
        assert axis["status"] == "incomplete"
        assert axis["score"] is None


def test_the_shipped_scenario_marks_cost_and_mass_against_a_survivable_machine():
    import yaml

    from scenario.runner import scenario_config_path

    config = yaml.safe_load(
        scenario_config_path("ssos_eclss_loop").read_text(encoding="utf-8")
    )
    footprint = config["evaluation"]["footprint"]
    assert footprint["cost_full_score_musd"] < footprint["cost_zero_score_musd"]
    assert footprint["mass_full_score_kg"] < footprint["mass_zero_score_kg"]


def test_where_the_marks_went_is_reported_worst_first():
    """A total says a design is worse; the breakdown says what to change."""
    from scenario.ssos_eclss_loop.unified_evaluation import compact_evaluation

    compact = compact_evaluation(
        {
            "status": "scored",
            "physics_gate": {"passed": True},
            "scores": {
                "total": 55.0,
                "max_score": 90,
                "axes": {
                    "actor_survival": {"score": 20.0, "max_score": 20, "status": "scored"},
                    "mass": {"score": 0.0, "max_score": 20, "status": "scored"},
                    "cost": {"score": 5.0, "max_score": 20, "status": "scored"},
                    "tcl": {"score": 10.0, "max_score": 10, "status": "scored"},
                },
            },
        }
    )
    assert [row["axis"] for row in compact["points_lost"]] == ["mass", "cost"]
    assert compact["points_lost"][0]["points"] == 20.0
    # A perfect axis is not listed: nothing was lost there.
    assert compact["axes"]["actor_survival"]["score"] == 20.0
