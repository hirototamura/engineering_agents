"""Unit tests for the findings computation and the HTML report.

The findings dictionary is the contract between the science and the document:
every number the prose quotes is pulled from it, so testing it is what keeps the
text from drifting away from the data.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from tools.analysis import report
from tools.analysis.loop_dynamics import ChainDynamics, IterationState

SCENARIO = {
    "plant_sim": {
        "time": {"step_seconds": 1200, "wrs_operation_seconds": 1200},
        "crew": {"size": 50, "activity_factor": 1.0, "co2_kg_day_person": 1.04,
                 "o2_kg_day_person": 0.84, "potable_water_kg_day_person": 2.28,
                 "urine_kg_day_person": 1.5, "condensate_kg_day_person": 0.75},
        "ars": {"capacity_kg_day": 4.5},
        "ogs": {"max_o2_kg_day": 9.25},
        "wrs": {"max_feed_l_per_operation": 10.0},
    },
    "design_constraints": {
        "budgets": {"max_total_mass_kg": 4000.0, "max_total_cost_musd": 500.0,
                    "max_total_volume_m3": 14.0},
    },
}


def surface_rows(n_ars: int = 8, n_ogs: int = 8):
    """A synthetic response surface with a known transition on each axis."""

    rows = []
    for i in range(n_ars):
        ars = 4.5 * (1 + i)
        for j in range(n_ogs):
            ogs = 9.25 * (1 + j)
            rho_ars, rho_ogs = ars / 52.0, ogs / 42.0
            survival = 1.0 if (rho_ars >= 0.5 and rho_ogs >= 1.0) else 0.0
            rows.append({
                "run_id": f"g{i}{j}", "ars": ars, "ogs": ogs,
                "rho_ars": rho_ars, "rho_ogs": rho_ogs,
                "rho_min": min(rho_ars, rho_ogs),
                "survival_fraction": survival,
                "evaluation_score": 20.0 + 70.0 * survival,
                "total_mass_kg": 1800.0 + 60.0 * (ars + ogs),
                "total_cost_musd": 259.0 + 8.0 * (ars + ogs),
                "total_volume_m3": 4.6 + 0.1 * (ars + ogs),
                "physics_gate_passed": True,
                "residual_o2_kg": 0.0, "residual_co2_kg": 0.0, "residual_water_l": 0.0,
                "tcl_seconds": 86400.0 if survival else 3600.0,
                "tcl_observed": survival < 1.0,
            })
    return rows


def oat_rows():
    rows = []
    for mult in (0.5, 1.0, 2.0, 4.0):
        rows.append({"axis": "ogs_max_o2_kg_day", "subspace": "capacity",
                     "multiplier": mult, "survival_fraction": 1.0 if mult >= 4.0 else 0.0,
                     "evaluation_score": 20.0})
        rows.append({"axis": "ogs_action_water_mass", "subspace": "action",
                     "multiplier": mult, "survival_fraction": 0.0,
                     "evaluation_score": 20.0,
                     "limited_oxygen_generation.ogs_capacity": 1.0 if mult >= 1.0 else 0.0})
    return rows


def chain(archetype_states=3):
    states = tuple(
        IterationState(
            iteration=k + 1, vector={}, survival_fraction=0.0, evaluation_score=23.0,
            rho_min=0.087, displacement=0.3865 * k,
            step_norm=0.0 if k == 0 else 0.3865,
            turning_cosine=None if k < 2 else 1.0,
            step_by_subspace={"capacity": 0.0, "action": 0.3865 if k else 0.0, "policy": 0.0},
            displacement_by_subspace={"capacity": 0.0, "action": 0.3865 * k, "policy": 0.0},
            proposed_kinds={"action_profile": 3, "set_parameter": 2},
            applied_kinds={"action_profile": 3},
        )
        for k in range(archetype_states)
    )
    return ChainDynamics(
        chain_id="chain-n03", design_mode="labeled_rule_base", states=states,
        archetype="saturating", total_displacement=states[-1].displacement,
        displacement_by_subspace=dict(states[-1].displacement_by_subspace),
        outcome_change=0.0,
        proposed_share={"action": 0.6, "policy": 0.4},
        applied_share={"action": 1.0},
        magnitude_share={"capacity": 0.0, "action": 1.0, "policy": 0.0},
        discarded_fraction=0.4, verdict="NOT_IMPROVED",
    )


def datasets():
    return {
        "seed_replicates": [
            {"evaluation_score": 23.0, "crew_remaining": 0, "seed": s} for s in (1, 2, 3)
        ],
        "response_surface": surface_rows(),
        "one_at_a_time": oat_rows(),
        "one_at_a_time_relieved": oat_rows(),
        "crew_scaling": [
            {"crew_size": n, "rho_min": 4.5 / (1.04 * n),
             "survival_fraction": 1.0 if n <= 8 else 0.0}
            for n in (4, 8, 16, 32, 50)
        ],
        "iso_ray": [
            {"scale": 50 / n, "rho_min": 4.5 * (50 / n) / 52.0,
             "survival_fraction": 1.0 if n <= 8 else 0.0}
            for n in (4, 8, 16, 32, 50)
        ],
        "chains": [],
    }


# --------------------------------------------------------------------------- #
# findings
# --------------------------------------------------------------------------- #
def test_analyse_reports_dataset_sizes():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    assert findings["dataset_sizes"]["response_surface"] == 64


def test_determinism_is_detected_from_zero_spread():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    assert findings["determinism"]["deterministic"] is True
    assert findings["determinism"]["spreads"]["evaluation_score"] == pytest.approx(0.0)


def test_determinism_is_not_claimed_when_seeds_disagree():
    data = datasets()
    data["seed_replicates"][0]["evaluation_score"] = 99.0
    findings = report.analyse(data, [chain()], config=SCENARIO)
    assert findings["determinism"]["deterministic"] is False


def test_physics_gate_pass_count_is_reported():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    assert findings["physics"]["gate_passed"] == findings["physics"]["gate_total"] == 64


def test_surface_counts_surviving_and_within_budget_designs():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    surface = findings["surface"]
    assert surface["n"] == 64
    assert surface["n_full_survival"] > 0
    assert surface["n_full_survival_within_budget"] <= surface["n_full_survival"]


def test_lightest_surviving_design_is_the_minimum_mass_among_survivors():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    survivors = [r for r in surface_rows() if r["survival_fraction"] >= 1.0]
    expected = min(r["total_mass_kg"] for r in survivors)
    assert findings["surface"]["lightest_full_survival"]["total_mass_kg"] == pytest.approx(expected)


def test_criticality_fits_each_available_profile():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    assert findings["criticality"]["fits"]
    for fit in findings["criticality"]["fits"].values():
        assert math.isfinite(fit["x0"])


def test_collapse_pairs_the_two_independent_sweeps():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    collapse = findings["collapse"]
    assert collapse["n_paired"] > 0
    assert collapse["max_abs_difference"] is not None


def test_controllability_separates_the_dead_axes():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    assert "ogs_action_water_mass" in findings["controllability"]["zero_gain_axes"]
    assert "ogs_max_o2_kg_day" not in findings["controllability"]["zero_gain_axes"]


def test_designer_magnitude_share_is_taken_from_the_chains():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    share = findings["controllability"]["designer_magnitude_share"]
    assert share["action"] == pytest.approx(1.0)
    assert share["capacity"] == pytest.approx(0.0)


def test_effective_gain_is_zero_when_the_actuated_subspace_is_dead():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    assert findings["controllability"]["effective_gain"]["action"] == pytest.approx(0.0)


def test_loop_archetype_distribution_sums_to_one():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    assert sum(findings["loop"]["archetypes"].values()) == pytest.approx(1.0)


def test_ruggedness_flags_a_monotone_surface_as_monotone():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    assert findings["ruggedness"]["monotone"] is True


def test_ruggedness_counts_a_deliberate_reversal():
    data = datasets()
    victim = max(data["response_surface"], key=lambda r: (r["ogs"], r["rho_ars"]))
    victim["survival_fraction"] = 0.0
    findings = report.analyse(data, [chain()], config=SCENARIO)
    assert findings["ruggedness"]["surface_descents"] >= 1
    assert findings["ruggedness"]["monotone"] is False


def test_survival_curves_are_grouped_by_coverage_regime():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    assert set(findings["survival"]["curves"]) <= {"rho_min < 0.5", "rho_min >= 0.5"}


# --------------------------------------------------------------------------- #
# predictive models
# --------------------------------------------------------------------------- #
def test_structured_model_beats_the_constant_baseline_out_of_sample():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    models = findings["predictive"]["models"]
    assert models["Liebig on response"]["r_squared"] > models["constant"]["r_squared"]


def test_every_declared_model_is_scored():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    assert set(findings["predictive"]["models"]) == set(report.MODEL_ORDER)


def test_train_and_test_partition_the_grid():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    predictive = findings["predictive"]
    assert predictive["n_train"] + predictive["n_test"] == predictive["n"]


def test_balanced_accuracy_of_the_constant_model_is_one_half():
    findings = report.analyse(datasets(), [chain()], config=SCENARIO)
    assert findings["predictive"]["models"]["constant"]["balanced_accuracy"] == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def test_render_produces_a_self_contained_document():
    data = datasets()
    chains = [chain()]
    document = report.render(report.analyse(data, chains, config=SCENARIO), data, chains)
    assert document.startswith("<!DOCTYPE html>")
    assert document.rstrip().endswith("</html>")
    assert "<svg" in document
    assert "<img" not in document  # no external assets
    assert 'src="http' not in document


def test_render_includes_every_figure():
    data = datasets()
    chains = [chain()]
    document = report.render(report.analyse(data, chains, config=SCENARIO), data, chains)
    assert document.count("<figure>") >= 8


def test_render_quotes_the_computed_budget_shortfall():
    data = datasets()
    chains = [chain()]
    findings = report.analyse(data, chains, config=SCENARIO)
    document = report.render(findings, data, chains)
    assert str(findings["surface"]["n_full_survival"]) in document


def test_render_survives_empty_datasets():
    empty = {name: [] for name in report.DATASET_NAMES}
    document = report.render(report.analyse(empty, [], config=SCENARIO), empty, [])
    assert "<!DOCTYPE html>" in document


def test_render_japanese_uses_ja_lang_and_translated_prose():
    data = datasets()
    chains = [chain()]
    findings = report.analyse(data, chains, config=SCENARIO)
    document = report.render(
        findings, data, chains, lang="ja", peer_href="design_loop_analysis.html",
    )
    assert 'lang="ja"' in document
    assert "設計エージェントの物理" in document
    assert "要約" in document
    assert "図 1." in document
    assert "実行不能" in document
    assert str(findings["surface"]["n_full_survival"]) in document
    assert "design_loop_analysis.html" in document
    assert "<img" not in document


def test_render_english_stays_the_default():
    data = datasets()
    chains = [chain()]
    document = report.render(report.analyse(data, chains, config=SCENARIO), data, chains)
    assert 'lang="en"' in document
    assert "Summary" in document
    assert "Figure 1." in document


def test_sibling_report_path_pairs_en_and_ja():
    en = Path("src/experiments/analysis/design_loop_analysis.html")
    ja = report.sibling_report_path(en, "ja")
    assert ja.name == "design_loop_analysis.ja.html"
    assert report.sibling_report_path(ja, "en") == en


def test_load_datasets_reads_what_the_campaign_wrote(tmp_path):
    (tmp_path / "datasets").mkdir()
    (tmp_path / "datasets" / "response_surface.json").write_text(json.dumps(surface_rows()))
    loaded = report.load_datasets(tmp_path)
    assert len(loaded["response_surface"]) == 64
    assert loaded["crew_scaling"] == []
