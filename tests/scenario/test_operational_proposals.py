"""Tests for operational_proposals.json apply/build helpers."""

import json

import pytest

from scenario.ssos_eclss_loop.operational_proposals import (
    apply_operational_proposals,
    build_operational_proposals_from_run,
    validate_operational_proposals,
    write_operational_proposals,
)


def test_apply_action_profile_and_service_config():
    config = {
        "agents": {"policy": {"ars_goal": {"initial_co2_mass": 1000.0}}},
        "thresholds": {"o2_storage_low_kg": 400.0},
    }
    proposals = {
        "proposed_by": "op_1",
        "decision_source": "rule",
        "changes": [
            {
                "change_kind": "action_profile",
                "payload": {
                    "subsystem": "ogs",
                    "fields": {"input_water_mass": 12.0, "iodine_concentration": 1.5},
                },
            },
            {
                "change_kind": "service_config",
                "payload": {"service": "request_co2", "amount": 30.0, "before_ogs": False},
            },
            {
                "change_kind": "set_parameter",
                "payload": {"target": "thresholds.co2_storage_high_kg", "value": 1600.0},
            },
        ],
    }
    merged = apply_operational_proposals(config, proposals)
    assert merged["agents"]["policy"]["ogs_goal"]["input_water_mass"] == 12.0
    assert merged["agents"]["policy"]["request_co2_amount"] == 30.0
    assert merged["agents"]["policy"]["request_co2_before_ogs"] is False
    assert merged["thresholds"]["co2_storage_high_kg"] == 1600.0
    assert merged["agents"]["policy"]["ars_goal"]["initial_co2_mass"] == 1000.0


def test_build_operational_proposals_from_policy():
    policy = {
        "co2_storage_high_kg": 1500.0,
        "o2_storage_low_kg": 450.0,
        "request_co2_amount": 25.0,
        "request_co2_before_ogs": True,
        "ars_goal": {"initial_co2_mass": 1800.0},
        "ogs_goal": {"input_water_mass": 10.0},
    }
    doc = build_operational_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy=policy,
    )
    assert doc["proposed_by"] == "eclss_operator_1"
    kinds = {c["change_kind"] for c in doc["changes"]}
    assert kinds == {"action_profile", "service_config", "set_parameter"}
    assert validate_operational_proposals(doc) == []


def test_write_rejects_invalid_change_kind(tmp_path):
    bad = {"changes": [{"change_kind": "add_edge", "payload": {}}]}
    with pytest.raises(ValueError, match="change_kind"):
        write_operational_proposals(tmp_path / "bad.json", bad)


def test_round_trip_via_json_file(tmp_path):
    proposals = build_operational_proposals_from_run(
        proposed_by="rep",
        decision_source="rule",
        policy={"ogs_goal": {"input_water_mass": 9.0}},
    )
    path = tmp_path / "operational_proposals.json"
    write_operational_proposals(path, proposals)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    merged = apply_operational_proposals({"agents": {"policy": {}}}, loaded)
    assert merged["agents"]["policy"]["ogs_goal"]["input_water_mass"] == 9.0
