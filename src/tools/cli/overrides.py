"""Parse CLI override flags into nested dicts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from scenario.runner import _deep_merge


def parse_set_values(values: List[str]) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(
                f"Invalid --set value {item!r}. Expected dot.key=value "
                "(example: simulation.steps=30)."
            )
        key, raw_value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid --set key in {item!r}.")
        _assign_dotted_key(overrides, key, _coerce_value(raw_value))
    return overrides


def load_override_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError(f"Override file must contain a mapping: {path}")
    return payload


def merge_overrides(*parts: Dict[str, Any] | None) -> Dict[str, Any] | None:
    merged: Dict[str, Any] = {}
    for part in parts:
        if not part:
            continue
        merged = _deep_merge(merged, part)
    return merged or None


def _assign_dotted_key(target: Dict[str, Any], dotted_key: str, value: Any) -> None:
    keys = dotted_key.split(".")
    cursor = target
    for key in keys[:-1]:
        existing = cursor.get(key)
        if existing is None:
            existing = {}
            cursor[key] = existing
        if not isinstance(existing, dict):
            raise ValueError(f"Cannot set nested key {dotted_key!r}: {key!r} is not a mapping.")
        cursor = existing
    cursor[keys[-1]] = value


def _coerce_value(raw_value: str) -> Any:
    lowered = raw_value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered == "null":
        return None
    try:
        if "." in raw_value:
            return float(raw_value)
        return int(raw_value)
    except ValueError:
        if (
            (raw_value.startswith('"') and raw_value.endswith('"'))
            or (raw_value.startswith("'") and raw_value.endswith("'"))
        ):
            return raw_value[1:-1]
        return raw_value
