"""Fail-closed gates from the trunk→main thermo-nuclear review."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.event_log import EventLog, looks_like_run_directory, remove_run_directory
from scenario.jobs.iterate import iterate_apply_document, resolve_iteration
from scenario.ssos_eclss_loop.design_eval import STATUS_REJECTED
from scenario.ssos_eclss_loop.design_proposals import (
    ALLOWED_SET_PARAMETER_TARGETS,
    apply_design_proposals,
)
from scenario.ssos_eclss_loop.evaluation_browser import AXIS_ORDER
from tools.analysis.artifacts import RunRecord
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


def test_evaluate_run_uses_the_telemetry_physics_gate():
    from scenario.ssos_eclss_loop import evaluation

    source = Path(evaluation.__file__).read_text(encoding="utf-8")
    assert "def _physics_gate(" not in source
    assert "evaluate_physics(telemetry)" in source


def test_analysis_residuals_read_ledger_checks():
    record = RunRecord(
        run_dir=Path("."),
        run_id="x",
        evaluation={
            "physics_gate": {
                "passed": True,
                "checks": [
                    {"name": "carbon_ledger", "residual": -0.2},
                    {"name": "oxygen_ledger", "residual": 0.0},
                    {"name": "water_ledger", "residual": 0.4},
                ],
            }
        },
    )
    assert record.mass_balance_residuals == {
        "co2_kg": 0.2,
        "o2_kg": 0.0,
        "water_l": 0.4,
    }


def test_approve_provisional_defaults_closed():
    settings = resolve_iteration({"iteration": {"enabled": False}})
    assert settings.approve_provisional is False


def test_rejected_final_is_not_applied_even_when_provisional_is_approved():
    assert (
        iterate_apply_document(
            {
                "design_domain": "ssos_graph",
                "final_status": STATUS_REJECTED,
                "changes": [
                    {
                        "change_kind": "capacity_profile",
                        "payload": {
                            "backend": "plant_sim",
                            "fields": {"plant_sim.ars.capacity_kg_day": 20.0},
                        },
                    }
                ],
            },
            approve_provisional=True,
        )
        is None
    )
