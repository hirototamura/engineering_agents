"""The three ECLSS capacity design variables and their action-payload sync.

Design doc §2.2 / §6: a post-run designer may size ARS / OGS / WRS *hardware*
throughput and nothing else. Recovery efficiencies, Sabatier conversion, crew
metabolism and health thresholds are explicitly NOT design variables — they are
material / safety / policy choices that would blur the sizing problem.

``capacity_profile`` proposals therefore write exactly these three scenario
paths::

    plant_sim.ars.capacity_kg_day
    plant_sim.ogs.max_o2_kg_day
    plant_sim.wrs.max_feed_l_per_operation

Raising nameplate capacity is not enough on its own: OGS is driven by the
actor's ``ogs_goal.input_water_mass`` and WRS by ``wrs_goal.urine_volume``
(design doc §6.1 / §6.2). ``sync_action_payloads`` raises those operational
payloads so a bigger machine is actually usable; it never lowers them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from environment.ssos.eclss.plant_sim.stoichiometry import WATER_PER_O2

SECONDS_PER_DAY = 86400.0

# Urine request headroom over the per-step production rate. Deliberately below
# the batch cap so condensate / grey water keeps a share of the same batch
# (``PlantModel.run_wrs`` gives grey only the capacity urine leaves behind).
WRS_URINE_REQUEST_MARGIN = 1.5


@dataclass(frozen=True)
class CapacityVariable:
    key: str
    subsystem: str
    path: Tuple[str, ...]
    unit: str
    description: str


CAPACITY_VARIABLES: Dict[str, CapacityVariable] = {
    "plant_sim.ars.capacity_kg_day": CapacityVariable(
        key="plant_sim.ars.capacity_kg_day",
        subsystem="ars",
        path=("plant_sim", "ars", "capacity_kg_day"),
        unit="kg/day",
        description="ARS CO2 removal throughput (nameplate).",
    ),
    "plant_sim.ogs.max_o2_kg_day": CapacityVariable(
        key="plant_sim.ogs.max_o2_kg_day",
        subsystem="ogs",
        path=("plant_sim", "ogs", "max_o2_kg_day"),
        unit="kg/day",
        description="OGS O2 generation cap (nameplate).",
    ),
    "plant_sim.wrs.max_feed_l_per_operation": CapacityVariable(
        key="plant_sim.wrs.max_feed_l_per_operation",
        subsystem="wrs",
        path=("plant_sim", "wrs", "max_feed_l_per_operation"),
        unit="L/operation",
        description="WRS urine + grey batch capacity per water_recovery action.",
    ),
}

CAPACITY_KEYS = tuple(CAPACITY_VARIABLES)

BASELINE_CAPACITY: Dict[str, float] = {
    "plant_sim.ars.capacity_kg_day": 4.50,
    "plant_sim.ogs.max_o2_kg_day": 9.25,
    "plant_sim.wrs.max_feed_l_per_operation": 10.0,
}


def _dig(config: Mapping[str, Any], path: Tuple[str, ...]) -> Any:
    cursor: Any = config
    for part in path:
        if not isinstance(cursor, Mapping) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor


def _write(config: Dict[str, Any], path: Tuple[str, ...], value: Any) -> None:
    cursor: Any = config
    for part in path[:-1]:
        nxt = cursor.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[part] = nxt
        cursor = nxt
    cursor[path[-1]] = value


def read_capacity_fields(config: Mapping[str, Any]) -> Dict[str, float]:
    """Current value of each design variable (falls back to the baseline)."""
    out: Dict[str, float] = {}
    for key, var in CAPACITY_VARIABLES.items():
        raw = _dig(config, var.path)
        try:
            out[key] = float(raw) if raw is not None else BASELINE_CAPACITY[key]
        except (TypeError, ValueError):
            out[key] = BASELINE_CAPACITY[key]
    return out


def validate_capacity_fields(fields: Any) -> List[str]:
    """Preflight: reject anything a candidate simulation could not honour."""
    errors: List[str] = []
    if not isinstance(fields, Mapping) or not fields:
        return ["capacity_profile.fields must be a non-empty object"]
    for key, value in fields.items():
        if key not in CAPACITY_VARIABLES:
            errors.append(
                f"{key!r} is not a design variable "
                f"(allowed: {', '.join(CAPACITY_KEYS)})"
            )
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            errors.append(f"{key} must be numeric, got {value!r}")
            continue
        if not math.isfinite(number):
            errors.append(f"{key} must be finite, got {value!r}")
        elif number <= 0.0:
            errors.append(f"{key} must be > 0, got {number}")
    return errors


def normalize_capacity_fields(fields: Mapping[str, Any]) -> Dict[str, float]:
    errors = validate_capacity_fields(fields)
    if errors:
        raise ValueError("; ".join(errors))
    return {key: float(value) for key, value in fields.items()}


def complete_capacity_fields(
    fields: Mapping[str, Any],
    installed: Mapping[str, Any],
) -> Dict[str, Any]:
    """Overlay named keys onto the installed machine. Omitted keys stay.

    Iterate applies one document onto fresh YAML. A partial profile would
    otherwise reset unnamed subsystems to the baseline. Filling from the
    machine that just flew keeps those values.
    """
    complete: Dict[str, Any] = {}
    for key in CAPACITY_KEYS:
        if key in fields:
            complete[key] = fields[key]
        elif key in installed:
            complete[key] = installed[key]
    return complete or dict(fields)


def apply_capacity_fields(
    config: Dict[str, Any],
    fields: Mapping[str, Any],
) -> Dict[str, float]:
    """Write validated capacity fields into a scenario config (in place).

    Keys not listed are left as they already are in *config*. Callers that
    start from fresh YAML must first complete the profile from the machine
    that was actually installed (see ``complete_capacity_fields``).
    """
    normalized = normalize_capacity_fields(fields)
    for key, value in normalized.items():
        _write(config, CAPACITY_VARIABLES[key].path, value)
    return normalized


# --------------------------------------------------------------------------- #
# operational payload sync (design doc §6.1 / §6.2)
# --------------------------------------------------------------------------- #
def _plant_time(config: Mapping[str, Any], key: str, default: float) -> float:
    raw = _dig(config, ("plant_sim", "time", key))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) and value > 0 else default


def required_ogs_input_water_mass(config: Mapping[str, Any]) -> float:
    """Water per OGS action needed to use the full O2 nameplate.

    ``ogs_goal.input_water_mass >= max_o2_kg_day * ogs_operation_seconds / 86400
    * WATER_PER_O2`` — below this the request throttles the machine and the
    capacity increase is invisible in the run.
    """
    capacity = read_capacity_fields(config)["plant_sim.ogs.max_o2_kg_day"]
    op_seconds = _plant_time(config, "ogs_operation_seconds", 1200.0)
    return capacity * op_seconds / SECONDS_PER_DAY * WATER_PER_O2


def expected_urine_l_per_step(config: Mapping[str, Any]) -> float:
    """Urine the crew produces in one observation interval."""
    crew = _dig(config, ("plant_sim", "crew")) or {}
    try:
        size = float(crew.get("size", 0.0))
        rate = float(crew.get("urine_kg_day_person", 1.50))
        activity = float(crew.get("activity_factor", 1.0))
    except (TypeError, ValueError):
        return 0.0
    step_seconds = _plant_time(config, "step_seconds", 1200.0)
    return size * rate * activity * step_seconds / SECONDS_PER_DAY


def required_wrs_urine_volume(config: Mapping[str, Any]) -> float:
    """Urine request per WRS action that keeps the buffer from growing.

    Capped by the batch size, and kept below it when possible so condensate /
    grey water still fits in the same batch.
    """
    max_feed = read_capacity_fields(config)["plant_sim.wrs.max_feed_l_per_operation"]
    wanted = expected_urine_l_per_step(config) * WRS_URINE_REQUEST_MARGIN
    if wanted <= 0.0:
        return min(max_feed, 0.5)
    return min(max_feed, wanted)


def policy_sinks(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Canonical ``agents.actor.policy`` plus the legacy ``agents.policy`` alias."""
    agents = config.setdefault("agents", {})
    legacy = agents.setdefault("policy", {})
    canonical = agents.setdefault("actor", {}).setdefault("policy", {})
    if canonical is legacy:
        return [canonical]
    return [legacy, canonical]


def sync_action_payloads(
    config: Dict[str, Any],
    *,
    policy_hint: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Dict[str, float]]:
    """Raise OGS / WRS action payloads so new capacity is actually reachable.

    Returns ``{"ogs_goal": {...}, "wrs_goal": {...}}`` describing what changed.
    Payloads are only ever raised: a run that already asks for more keeps its
    value, so an operator profile tuned by hand is not silently shrunk.
    """
    required_water = required_ogs_input_water_mass(config)
    required_urine = required_wrs_urine_volume(config)
    changed: Dict[str, Dict[str, float]] = {}

    sinks = policy_sinks(config)
    hint = dict(policy_hint or {})

    def current(goal: str, field: str, default: float) -> float:
        for sink in sinks:
            block = sink.get(goal)
            if isinstance(block, Mapping) and field in block:
                try:
                    return float(block[field])
                except (TypeError, ValueError):
                    continue
        block = hint.get(goal)
        if isinstance(block, Mapping) and field in block:
            try:
                return float(block[field])
            except (TypeError, ValueError):
                pass
        return default

    water_before = current("ogs_goal", "input_water_mass", 0.0)
    if required_water > water_before + 1e-12:
        for sink in sinks:
            sink.setdefault("ogs_goal", {})["input_water_mass"] = required_water
        changed["ogs_goal"] = {
            "input_water_mass": required_water,
            "previous_input_water_mass": water_before,
        }

    urine_before = current("wrs_goal", "urine_volume", 0.0)
    if required_urine > urine_before + 1e-12:
        for sink in sinks:
            sink.setdefault("wrs_goal", {})["urine_volume"] = required_urine
        changed["wrs_goal"] = {
            "urine_volume": required_urine,
            "previous_urine_volume": urine_before,
        }
    return changed


__all__ = [
    "BASELINE_CAPACITY",
    "CAPACITY_KEYS",
    "CAPACITY_VARIABLES",
    "CapacityVariable",
    "apply_capacity_fields",
    "complete_capacity_fields",
    "expected_urine_l_per_step",
    "normalize_capacity_fields",
    "policy_sinks",
    "read_capacity_fields",
    "required_ogs_input_water_mass",
    "required_wrs_urine_volume",
    "sync_action_payloads",
    "validate_capacity_fields",
]
