"""Fail-closed gates from the trunk→main thermo-nuclear review."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.event_log import EventLog, looks_like_run_directory, remove_run_directory
from scenario.ssos_eclss_loop.design_proposals import (
    ALLOWED_SET_PARAMETER_TARGETS,
    apply_design_proposals,
)
from scenario.ssos_eclss_loop.evaluation_browser import AXIS_ORDER
from scenario.ssos_eclss_loop.integrity_guard import evidence_status, integrity_summary
from tools.cli.overrides import unknown_override_paths


def test_thresholds_cannot_be_applied_as_set_parameter():
    assert all(not target.startswith("thresholds.") for target in ALLOWED_SET_PARAMETER_TARGETS)
    with pytest.raises(ValueError, match="not allowed"):
        apply_design_proposals(
            {"thresholds": {"co2_storage_high_kg": 2.0}},
            {
                "design_domain": "ssos_graph",
                "final_status": "approved_final",
                "changes": [
                    {
                        "change_kind": "set_parameter",
                        "payload": {"target": "thresholds.co2_storage_high_kg", "value": 99.0},
                    }
                ],
            },
        )


def test_missing_final_status_is_blocking():
    with pytest.raises(ValueError, match="unevaluated"):
        apply_design_proposals(
            {"plant_sim": {"ars": {"capacity_kg_day": 4.5}}},
            {
                "design_domain": "ssos_graph",
                "changes": [
                    {
                        "change_kind": "capacity_profile",
                        "payload": {
                            "backend": "plant_sim",
                            "fields": {"plant_sim.ars.capacity_kg_day": 30.0},
                        },
                    }
                ],
            },
        )


def test_empty_integrity_is_unknown_evidence():
    assert evidence_status({}) == "unknown"
    assert integrity_summary(None)["measured"] is False


def test_scorecard_browser_includes_cost_and_mass():
    assert "cost" in AXIS_ORDER
    assert "mass" in AXIS_ORDER


def test_unknown_override_paths_are_reported():
    unknown = unknown_override_paths(
        {"simulation": {"steps": 8}},
        {"this": {"key": {"does": {"not": {"exist": 1}}}}},
    )
    assert unknown == ["this"]


def test_prepare_run_dir_refuses_a_non_run_tree(tmp_path: Path):
    alien = tmp_path / "notes"
    alien.mkdir()
    (alien / "readme.txt").write_text("keep me\n", encoding="utf-8")
    assert looks_like_run_directory(alien) is False
    with pytest.raises(ValueError, match="not a simulation run directory"):
        EventLog.prepare_run_dir(tmp_path, "notes")
    assert (alien / "readme.txt").is_file()

    remove_run_directory(alien, force=True)
    assert not alien.exists()
    recreated = EventLog.prepare_run_dir(tmp_path, "notes")
    (recreated / "summary.json").write_text("{}", encoding="utf-8")
    EventLog.prepare_run_dir(tmp_path, "notes")
    assert recreated.is_dir()
