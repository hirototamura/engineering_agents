"""operational_proposals.json — post-run operational changes for the next ssos_eclss_loop run."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

OPERATIONAL_CHANGE_KINDS = frozenset({"set_parameter", "action_profile", "service_config"})


def load_operational_proposals(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("operational_proposals.json must be a JSON object")
    return data


def validate_operational_proposals(data: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    changes = data.get("changes")
    if not isinstance(changes, list):
        return ["changes must be a list"]
    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            errors.append(f"changes[{index}] must be an object")
            continue
        kind = change.get("change_kind")
        if kind not in OPERATIONAL_CHANGE_KINDS:
            errors.append(
                f"changes[{index}].change_kind must be one of {sorted(OPERATIONAL_CHANGE_KINDS)}"
            )
        payload = change.get("payload")
        if payload is not None and not isinstance(payload, dict):
            errors.append(f"changes[{index}].payload must be an object")
    return errors


def apply_operational_proposals(
    config: Dict[str, Any],
    proposals: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge proposal changes into scenario config for the *next* run."""
    errors = validate_operational_proposals(proposals)
    if errors:
        raise ValueError("; ".join(errors))

    merged = copy.deepcopy(config)
    for change in proposals.get("changes", []):
        kind = change["change_kind"]
        payload = change.get("payload") or {}
        if kind == "action_profile":
            _apply_action_profile(merged, payload)
        elif kind == "service_config":
            _apply_service_config(merged, payload)
        elif kind == "set_parameter":
            _apply_set_parameter(merged, payload)
    return merged


def _apply_action_profile(config: Dict[str, Any], payload: Dict[str, Any]) -> None:
    subsystem = str(payload.get("subsystem", "")).lower()
    fields = payload.get("fields") or {}
    if not isinstance(fields, dict):
        raise ValueError("action_profile.fields must be an object")
    policy = config.setdefault("agents", {}).setdefault("policy", {})
    if subsystem == "ars":
        policy.setdefault("ars_goal", {}).update(fields)
    elif subsystem == "ogs":
        policy.setdefault("ogs_goal", {}).update(fields)
    else:
        raise ValueError(f"action_profile subsystem must be ars or ogs, got {subsystem!r}")


def _apply_service_config(config: Dict[str, Any], payload: Dict[str, Any]) -> None:
    service = str(payload.get("service", "")).lower()
    policy = config.setdefault("agents", {}).setdefault("policy", {})
    if service == "request_co2":
        if "amount" in payload:
            policy["request_co2_amount"] = float(payload["amount"])
        if "before_ogs" in payload:
            policy["request_co2_before_ogs"] = bool(payload["before_ogs"])
    elif service == "request_o2":
        if "amount" in payload:
            policy["request_o2_amount"] = float(payload["amount"])
    else:
        raise ValueError(f"unsupported service_config service: {service!r}")


def _apply_set_parameter(config: Dict[str, Any], payload: Dict[str, Any]) -> None:
    target = str(payload.get("target", ""))
    value = payload.get("value")
    if not target:
        raise ValueError("set_parameter.target is required")

    parts = target.split(".")
    cursor: Any = config
    for part in parts[:-1]:
        if part not in cursor or not isinstance(cursor[part], dict):
            cursor[part] = {}
        cursor = cursor[part]
    cursor[parts[-1]] = value


def build_operational_proposals_from_run(
    *,
    proposed_by: str,
    decision_source: str,
    policy: Dict[str, Any],
    message: str = "Operational profiles observed during the run.",
) -> Dict[str, Any]:
    """Capture labeled-rule policy used at runtime as next-run proposals."""
    changes: List[Dict[str, Any]] = []

    ars_goal = policy.get("ars_goal") or {}
    if ars_goal:
        changes.append(
            {
                "change_kind": "action_profile",
                "payload": {
                    "subsystem": "ars",
                    "action": "air_revitalisation",
                    "fields": dict(ars_goal),
                },
            }
        )

    ogs_goal = policy.get("ogs_goal") or {}
    if ogs_goal:
        changes.append(
            {
                "change_kind": "action_profile",
                "payload": {
                    "subsystem": "ogs",
                    "action": "oxygen_generation",
                    "fields": dict(ogs_goal),
                },
            }
        )

    if "request_co2_amount" in policy or "request_co2_before_ogs" in policy:
        changes.append(
            {
                "change_kind": "service_config",
                "payload": {
                    "service": "request_co2",
                    "amount": float(policy.get("request_co2_amount", 25.0)),
                    "before_ogs": bool(policy.get("request_co2_before_ogs", True)),
                },
            }
        )

    for key in ("co2_storage_high_kg", "o2_storage_low_kg", "product_water_low_l"):
        if key in policy:
            value = float(policy[key])
            changes.append(
                {
                    "change_kind": "set_parameter",
                    "payload": {"target": f"agents.policy.{key}", "value": value},
                }
            )
            changes.append(
                {
                    "change_kind": "set_parameter",
                    "payload": {"target": f"thresholds.{key}", "value": value},
                }
            )

    return {
        "proposed_by": proposed_by,
        "decision_source": decision_source,
        "message": message,
        "changes": changes,
    }


def write_operational_proposals(path: Path, proposals: Dict[str, Any]) -> None:
    errors = validate_operational_proposals(proposals)
    if errors:
        raise ValueError("; ".join(errors))
    path.write_text(json.dumps(proposals, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
