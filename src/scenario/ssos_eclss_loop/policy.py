"""Labeled-rule policy helpers for ssos_eclss_loop."""

from __future__ import annotations

import copy
from typing import Any, Dict

# Verification thresholds mirrored into labeled_rule_base policy (not LLM prompts).
THRESHOLD_POLICY_KEYS = (
    "co2_storage_high_kg",
    "co2_storage_critical_kg",
    "o2_storage_low_kg",
    "product_water_low_l",
)


def merge_labeled_policy_from_thresholds(
    agents_config: Dict[str, Any],
    thresholds: Dict[str, Any],
) -> Dict[str, Any]:
    """Derive labeled_rule_base policy band keys from scenario verification thresholds."""
    if agents_config.get("mode") != "labeled_rule_base":
        return agents_config

    merged = copy.deepcopy(agents_config)
    policy = merged.setdefault("policy", {})
    for key in THRESHOLD_POLICY_KEYS:
        if key in thresholds:
            policy[key] = thresholds[key]
    return merged
