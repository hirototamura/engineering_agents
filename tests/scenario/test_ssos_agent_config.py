"""Tests for nested ssos actor / design agent config."""

from scenario.ssos_eclss_loop.agent_config import (
    flatten_actor_config,
    flatten_design_config,
    normalize_ssos_agents_section,
    resolve_ssos_modes,
    ssos_agents_enabled,
)
from scenario.ssos_eclss_loop.policy import merge_labeled_policy_from_thresholds


def test_legacy_mode_overrides_existing_actor_mode():
    normalized = normalize_ssos_agents_section(
        {"mode": "labeled_rule_base", "actor": {"mode": "none"}}
    )
    actor_mode, design_mode = resolve_ssos_modes(normalized)
    assert actor_mode == "labeled_rule_base"
    assert design_mode == "labeled_rule_base"


def test_legacy_mode_lifts_to_actor_and_design_inherits():
    normalized = normalize_ssos_agents_section({"mode": "labeled_rule_base", "team": {"count": 4}})
    actor_mode, design_mode = resolve_ssos_modes(normalized)
    assert actor_mode == "labeled_rule_base"
    assert design_mode == "labeled_rule_base"
    assert normalized["actor"]["team"]["count"] == 4


def test_explicit_design_none_does_not_inherit():
    actor_mode, design_mode = resolve_ssos_modes(
        {"actor": {"mode": "llm"}, "design": {"mode": "none"}}
    )
    assert actor_mode == "llm"
    assert design_mode == "none"


def test_ssos_agents_enabled_design_only():
    assert ssos_agents_enabled({"actor": {"mode": "none"}, "design": {"mode": "llm"}})
    assert not ssos_agents_enabled({"actor": {"mode": "none"}, "design": {"mode": "none"}})


def test_flatten_keeps_nested_modes():
    cfg = {
        "actor": {"mode": "labeled_rule_base", "policy": {"request_co2_amount": 0.02}},
        "design": {"mode": "llm", "team": {"count": 4}},
    }
    assert flatten_actor_config(cfg)["mode"] == "labeled_rule_base"
    assert flatten_design_config(cfg)["mode"] == "llm"


def test_merge_labeled_policy_nested_actor():
    agents_config = {
        "actor": {"mode": "labeled_rule_base", "policy": {"request_co2_amount": 0.025}},
        "design": {"mode": "labeled_rule_base"},
    }
    merged = merge_labeled_policy_from_thresholds(
        agents_config,
        {"co2_storage_high_kg": 1.55, "o2_storage_low_kg": 0.44},
    )
    assert merged["actor"]["policy"]["co2_storage_high_kg"] == 1.55
    assert merged["actor"]["policy"]["request_co2_amount"] == 0.025
