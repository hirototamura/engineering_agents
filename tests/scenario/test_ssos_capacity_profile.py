"""capacity_profile design variables and payload sync (design doc §6)."""

from __future__ import annotations

import copy

import pytest
import yaml

from scenario.runner import scenario_config_path
from scenario.ssos_eclss_loop.design_proposals import (
    SSOS_CHANGE_KINDS,
    apply_design_proposals,
    validate_design_proposals,
    validate_ssos_proposal_change,
)
from scenario.ssos_eclss_loop.design_variables import (
    CAPACITY_KEYS,
    expected_urine_l_per_step,
    read_capacity_fields,
    required_ogs_input_water_mass,
    sync_action_payloads,
    validate_capacity_fields,
)


def _scenario_config() -> dict:
    with scenario_config_path("ssos_eclss_loop").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _proposal(fields: dict, **payload) -> dict:
    return {
        "design_domain": "ssos_graph",
        "changes": [
            {
                "change_kind": "capacity_profile",
                "payload": {"backend": "plant_sim", "fields": fields, **payload},
            }
        ],
    }


def test_capacity_profile_is_a_supported_change_kind():
    assert "capacity_profile" in SSOS_CHANGE_KINDS
    # the classic kinds still exist (backwards compatibility, design doc §11)
    assert {"action_profile", "service_config", "set_parameter", "graph_rewire"} <= SSOS_CHANGE_KINDS


def test_apply_writes_the_three_design_variables():
    config = _scenario_config()
    fields = {
        "plant_sim.ars.capacity_kg_day": 21.0,
        "plant_sim.ogs.max_o2_kg_day": 45.0,
        "plant_sim.wrs.max_feed_l_per_operation": 2.5,
    }
    merged = apply_design_proposals(config, _proposal(fields))
    assert merged["plant_sim"]["ars"]["capacity_kg_day"] == pytest.approx(21.0)
    assert merged["plant_sim"]["ogs"]["max_o2_kg_day"] == pytest.approx(45.0)
    assert merged["plant_sim"]["wrs"]["max_feed_l_per_operation"] == pytest.approx(2.5)
    # untouched physics
    assert merged["plant_sim"]["ars"]["capture_efficiency"] == pytest.approx(
        config["plant_sim"]["ars"]["capture_efficiency"]
    )
    assert merged["plant_sim"]["crew"]["size"] == config["plant_sim"]["crew"]["size"]


@pytest.mark.parametrize(
    "fields",
    [
        {"plant_sim.ars.capture_efficiency": 0.99},
        {"plant_sim.crew.co2_kg_day_person": 0.5},
        {"plant_sim.wrs.urine_recovery": 1.0},
        {"thresholds.co2_storage_critical_kg": 99.0},
        {"plant_sim.ars.capacity_kg_day": -1.0},
        {"plant_sim.ogs.max_o2_kg_day": float("inf")},
        {"plant_sim.ogs.max_o2_kg_day": "big"},
        {},
    ],
)
def test_out_of_scope_or_bad_fields_are_rejected(fields):
    assert validate_capacity_fields(fields)
    assert validate_ssos_proposal_change(
        "capacity_profile", {"backend": "plant_sim", "fields": fields}
    ) is None
    with pytest.raises(ValueError):
        apply_design_proposals(_scenario_config(), _proposal(fields))


def test_unknown_backend_is_rejected():
    assert validate_ssos_proposal_change(
        "capacity_profile",
        {"backend": "ros2", "fields": {"plant_sim.ars.capacity_kg_day": 10.0}},
    ) is None


def test_ogs_payload_is_synced_so_the_nameplate_is_reachable():
    config = _scenario_config()
    before = float(config["agents"]["actor"]["policy"]["ogs_goal"]["input_water_mass"]) if (
        config.get("agents", {}).get("actor", {}).get("policy")
    ) else 0.15
    merged = apply_design_proposals(config, _proposal({"plant_sim.ogs.max_o2_kg_day": 42.0}))
    synced = merged["agents"]["actor"]["policy"]["ogs_goal"]["input_water_mass"]
    assert synced == pytest.approx(required_ogs_input_water_mass(merged))
    assert synced > before
    # legacy alias stays in lock-step
    assert merged["agents"]["policy"]["ogs_goal"]["input_water_mass"] == pytest.approx(synced)


def test_wrs_payload_covers_the_urine_produced_each_step():
    config = _scenario_config()
    merged = apply_design_proposals(
        config, _proposal({"plant_sim.wrs.max_feed_l_per_operation": 3.0})
    )
    urine_volume = merged["agents"]["actor"]["policy"]["wrs_goal"]["urine_volume"]
    assert urine_volume >= expected_urine_l_per_step(merged)
    # leaves batch room for condensate / grey water
    assert urine_volume <= merged["plant_sim"]["wrs"]["max_feed_l_per_operation"]


def test_sync_never_lowers_a_hand_tuned_payload():
    config = _scenario_config()
    config.setdefault("agents", {}).setdefault("actor", {}).setdefault("policy", {})[
        "ogs_goal"
    ] = {"input_water_mass": 99.0}
    merged = copy.deepcopy(config)
    sync_action_payloads(merged)
    assert merged["agents"]["actor"]["policy"]["ogs_goal"]["input_water_mass"] == 99.0


def test_sync_can_be_disabled_per_proposal():
    config = _scenario_config()
    before = read_capacity_fields(config)
    merged = apply_design_proposals(
        config,
        _proposal({"plant_sim.ogs.max_o2_kg_day": 42.0}, sync_action_payloads=False),
    )
    assert merged["plant_sim"]["ogs"]["max_o2_kg_day"] == 42.0
    assert before["plant_sim.ogs.max_o2_kg_day"] != 42.0
    policy = (merged.get("agents", {}).get("actor", {}) or {}).get("policy") or {}
    assert "ogs_goal" not in policy or policy["ogs_goal"].get("input_water_mass") != pytest.approx(
        required_ogs_input_water_mass(merged)
    )


def test_capacity_keys_are_exactly_the_three_design_variables():
    assert set(CAPACITY_KEYS) == {
        "plant_sim.ars.capacity_kg_day",
        "plant_sim.ogs.max_o2_kg_day",
        "plant_sim.wrs.max_feed_l_per_operation",
    }


def test_document_with_capacity_profile_validates():
    doc = _proposal({"plant_sim.ars.capacity_kg_day": 21.0})
    assert validate_design_proposals(doc) == []
