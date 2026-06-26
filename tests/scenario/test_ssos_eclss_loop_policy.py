"""Tests for labeled policy derivation from scenario thresholds."""

from scenario.ssos_eclss_loop.policy import merge_labeled_policy_from_thresholds


def test_merge_labeled_policy_from_thresholds_copies_bands():
    agents_config = {
        "mode": "labeled_rule_base",
        "policy": {
            "request_co2_amount": 25.0,
            "ars_goal": {"initial_co2_mass": 1800.0},
        },
    }
    thresholds = {
        "co2_storage_high_kg": 1550.0,
        "o2_storage_low_kg": 440.0,
        "product_water_low_l": 55.0,
    }
    merged = merge_labeled_policy_from_thresholds(agents_config, thresholds)
    assert merged["policy"]["co2_storage_high_kg"] == 1550.0
    assert merged["policy"]["o2_storage_low_kg"] == 440.0
    assert merged["policy"]["product_water_low_l"] == 55.0
    assert merged["policy"]["request_co2_amount"] == 25.0


def test_merge_labeled_policy_skips_llm_mode():
    agents_config = {"mode": "llm", "policy": {"co2_storage_high_kg": 999.0}}
    merged = merge_labeled_policy_from_thresholds(
        agents_config,
        {"co2_storage_high_kg": 1500.0},
    )
    assert merged["policy"]["co2_storage_high_kg"] == 999.0
