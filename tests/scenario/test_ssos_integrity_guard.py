"""Scoring Integrity Guard (spec §11, §18.1)."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from scenario.ssos_eclss_loop.integrity_guard import (
    classify_path,
    compare_configs,
    evidence_status,
    integrity_summary,
)


def _scenario() -> dict:
    path = Path(__file__).parents[2] / "src" / "scenario" / "ssos_eclss_loop" / "scenario.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _with(**changes) -> tuple[dict, dict]:
    """A pristine config and a copy carrying one change, by dotted path."""
    pristine = _scenario()
    effective = copy.deepcopy(pristine)
    for path, value in changes.items():
        node = effective
        parts = path.split(".")
        for key in parts[:-1]:
            node = node[key]
        node[parts[-1]] = value
    return pristine, effective


def test_an_untouched_run_reports_no_modification():
    pristine = _scenario()
    result = compare_configs(pristine, copy.deepcopy(pristine))

    assert result["scoring_bar_modified"] is False
    assert result["operating_point_modified"] is False
    assert result["arm_modified"] is False
    assert result["changed_paths"] == {
        "scoring_bar": [],
        "operating_point": [],
        "arm": [],
        "other": [],
    }


def test_loosening_a_threshold_invalidates_the_run_as_evidence():
    pristine, effective = _with(**{"thresholds.co2_storage_critical_kg": 99.0})
    result = compare_configs(pristine, effective)

    assert result["scoring_bar_modified"] is True
    assert result["changed_paths"]["scoring_bar"] == ["thresholds.co2_storage_critical_kg"]
    assert evidence_status(result) == "invalid"


def test_a_capacity_change_is_recorded_but_not_refused():
    """Resizing the hardware is the point of the design loop."""
    pristine, effective = _with(**{"plant_sim.ars.capacity_kg_day": 23.92})
    result = compare_configs(pristine, effective)

    assert result["operating_point_modified"] is True
    assert result["scoring_bar_modified"] is False
    assert result["changed_paths"]["operating_point"] == ["plant_sim.ars.capacity_kg_day"]
    assert evidence_status(result) == "valid"


def test_an_operating_policy_change_is_recorded_as_arm():
    pristine = _scenario()
    effective = copy.deepcopy(pristine)
    effective.setdefault("agents", {}).setdefault("actor", {})["mode"] = "llm"
    result = compare_configs(pristine, effective)

    assert result["arm_modified"] is True
    assert result["scoring_bar_modified"] is False
    assert evidence_status(result) == "valid"


def test_a_change_anywhere_under_a_guarded_subtree_is_caught():
    """Enumerating fields misses the neighbour; subtree diffing does not."""
    pristine = _scenario()
    effective = copy.deepcopy(pristine)
    effective["plant_sim"]["survival"]["co2"]["critical_steps"] = 99
    effective["thresholds"]["a_threshold_added_later"] = 1.0

    result = compare_configs(pristine, effective)
    assert result["scoring_bar_modified"] is True
    assert set(result["changed_paths"]["scoring_bar"]) == {
        "plant_sim.survival.co2.critical_steps",
        "thresholds.a_threshold_added_later",
    }


def test_shrinking_the_crew_is_a_scoring_bar_change():
    """Fewer people is an easier run, not a better design."""
    pristine, effective = _with(**{"plant_sim.crew.size": 4})
    assert compare_configs(pristine, effective)["scoring_bar_modified"] is True


def test_starting_with_a_fuller_tank_is_a_scoring_bar_change():
    pristine, effective = _with(**{"simulation.initial_o2_storage_kg": 500.0})
    assert compare_configs(pristine, effective)["scoring_bar_modified"] is True


def test_raising_the_adoption_budget_is_a_scoring_bar_change():
    """A design that cannot fit the budget must not be able to widen it."""
    pristine = _scenario()
    effective = copy.deepcopy(pristine)
    effective["design_constraints"]["budgets"]["max_total_mass_kg"] = 99999.0
    assert compare_configs(pristine, effective)["scoring_bar_modified"] is True


def test_an_unclassified_change_is_still_reported():
    pristine = _scenario()
    effective = copy.deepcopy(pristine)
    effective["some_new_top_level_block"] = {"x": 1}

    result = compare_configs(pristine, effective)
    assert result["changed_paths"]["other"] == ["some_new_top_level_block"]
    assert result["scoring_bar_modified"] is False


def test_removed_and_added_keys_are_both_differences():
    pristine = _scenario()
    effective = copy.deepcopy(pristine)
    del effective["thresholds"]["o2_storage_low_kg"]
    assert compare_configs(pristine, effective)["scoring_bar_modified"] is True


def test_classification_prefers_the_more_specific_subtree():
    assert classify_path("plant_sim.ars.capacity_kg_day") == "operating_point"
    assert classify_path("plant_sim.survival.co2.warning_steps") == "scoring_bar"
    assert classify_path("agents.actor.policy.wrs_feed_trigger_l") == "arm"
    assert classify_path("output.formats") == "other"


def test_summary_block_carries_only_the_three_flags():
    pristine, effective = _with(**{"plant_sim.ogs.max_o2_kg_day": 48.3})
    assert integrity_summary(compare_configs(pristine, effective)) == {
        "scoring_bar_modified": False,
        "operating_point_modified": True,
        "arm_modified": False,
    }
