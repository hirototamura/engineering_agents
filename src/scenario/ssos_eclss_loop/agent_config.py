"""Resolve nested ssos_eclss_loop actor / design agent config."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

VALID_AGENT_MODES = frozenset({"none", "labeled_rule_base", "llm"})

_LEGACY_ACTOR_KEYS = (
    "mode",
    "team",
    "llm",
    "policy",
    "memory_limit",
    "discourse_window",
    "max_actions_per_step",
)


def normalize_ssos_agents_section(section: Dict[str, Any]) -> Dict[str, Any]:
    """Lift legacy flat ``agents.mode`` / ``agents.team`` into ``actor`` / ``design``."""
    actor = dict(section.get("actor") or {})
    design = dict(section.get("design") or {})
    if "mode" in section:
        actor["mode"] = section["mode"]
    for key in _LEGACY_ACTOR_KEYS:
        if key == "mode":
            continue
        if key in section and key not in actor:
            actor[key] = section[key]
    out = {
        k: v
        for k, v in section.items()
        if k not in _LEGACY_ACTOR_KEYS and k not in {"actor", "design", "config_file"}
    }
    out["actor"] = actor
    out["design"] = design
    return out


def resolve_ssos_modes(agents_config: Dict[str, Any]) -> Tuple[str, str]:
    actor = agents_config.get("actor") or {}
    design = agents_config.get("design") or {}
    actor_mode = str(actor.get("mode") or "none")
    design_raw = design.get("mode")
    design_mode = actor_mode if design_raw is None else str(design_raw)
    return actor_mode, design_mode


def flatten_actor_config(agents_config: Dict[str, Any]) -> Dict[str, Any]:
    actor = dict(agents_config.get("actor") or {})
    actor_mode, _ = resolve_ssos_modes(agents_config)
    actor["mode"] = actor_mode
    return actor


def flatten_design_config(agents_config: Dict[str, Any]) -> Dict[str, Any]:
    design = dict(agents_config.get("design") or {})
    _, design_mode = resolve_ssos_modes(agents_config)
    design["mode"] = design_mode
    return design


def ssos_agents_enabled(agents_config: Optional[Dict[str, Any]]) -> bool:
    if not agents_config:
        return False
    actor_mode, design_mode = resolve_ssos_modes(agents_config)
    return actor_mode != "none" or design_mode != "none"
