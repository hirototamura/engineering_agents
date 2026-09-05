"""Telemetry-only physics audit of a completed run (spec §12).

The gate answers one question: is this run admissible as physical evidence?
It reads ``telemetry.jsonl`` and nothing else -- no scenario config, no agent
config, no action results. A run that can only be judged by consulting the
settings it was produced from is not independently auditable, and a design
agent free to change those settings could otherwise move the bar it is
measured against.

Dependency direction is fixed::

    simulator -> telemetry -> this gate

Each check reports ``passed``, ``failed`` or ``skipped``. ``skipped`` is not a
pass: a quantity that could not be measured is reported as unmeasured, so a run
recorded before the audit fields existed reads as ``incomplete`` rather than
silently clean.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from environment.ssos.eclss.plant_sim.stoichiometry import (
    CH4_PER_H2,
    CO2_PER_H2,
    H2O_PER_H2,
    H2_PER_O2,
    WATER_PER_O2,
)

PASSED = "passed"
FAILED = "failed"
SKIPPED = "skipped"
INCOMPLETE = "incomplete"

INVENTORY_TOLERANCE = 1e-9
LEDGER_TOLERANCE = 2e-6
STOICHIOMETRY_TOLERANCE = 1e-6
CAPACITY_TOLERANCE = 1e-9
SECONDS_PER_DAY = 86400.0

STORAGE_FIELDS = (
    "co2_storage_kg",
    "o2_storage_kg",
    "product_water_reserve_l",
    "grey_water_collected_l",
)
PLANT_INVENTORY_FIELDS = ("captured_co2_kg", "urine_buffer_l", "crew_alive")
SUBSYSTEMS = ("ars", "ogs", "wrs")

CHECK_NAMES = (
    "readings_present_and_finite",
    "inventories_non_negative",
    "totals_monotonic",
    "carbon_ledger",
    "oxygen_ledger",
    "water_ledger",
    "stoichiometric_residual",
    "failure_quiescence",
    "capacity_bounds",
)


# --------------------------------------------------------------------------- #
# small helpers -- deliberately local, so the gate imports no evaluation code
# --------------------------------------------------------------------------- #
def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _number(value: Any) -> float:
    return float(value) if _finite(value) else 0.0


def _required_floats(
    mapping: Mapping[str, Any], keys: Sequence[str]
) -> Optional[Dict[str, float]]:
    """Return named finite floats, or None if any required term is missing."""
    out: Dict[str, float] = {}
    for key in keys:
        value = mapping.get(key)
        if not _finite(value):
            return None
        out[key] = float(value)
    return out


def _plant(row: Mapping[str, Any]) -> Mapping[str, Any]:
    topics = row.get("raw_topics")
    plant = topics.get("plant_sim") if isinstance(topics, Mapping) else None
    return plant if isinstance(plant, Mapping) else {}


def _check(name: str, status: str, reason: Optional[str] = None, **details: Any) -> Dict[str, Any]:
    return {"name": name, "status": status, "reason": reason, "details": details}


def read_telemetry(run_dir: Path) -> List[Dict[str, Any]]:
    path = Path(run_dir) / "telemetry.jsonl"
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


# --------------------------------------------------------------------------- #
# 1-2. readings and inventories
# --------------------------------------------------------------------------- #
def _readings_present_and_finite(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    missing: List[Dict[str, Any]] = []
    for row in rows:
        plant = _plant(row)
        for field in STORAGE_FIELDS:
            if not _finite(row.get(field)):
                missing.append({"step": row.get("step"), "field": field, "value": row.get(field)})
        for field in PLANT_INVENTORY_FIELDS:
            if not _finite(plant.get(field)):
                missing.append(
                    {
                        "step": row.get("step"),
                        "field": "plant_sim." + field,
                        "value": plant.get(field),
                    }
                )
    if missing:
        return _check(
            "readings_present_and_finite",
            FAILED,
            str(len(missing)) + " non-finite or missing readings",
            samples=missing[:10],
        )
    return _check("readings_present_and_finite", PASSED, rows=len(rows))


def _inventories_non_negative(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    negative: List[Dict[str, Any]] = []
    for row in rows:
        plant = _plant(row)
        for field in STORAGE_FIELDS:
            value = row.get(field)
            if _finite(value) and float(value) < -INVENTORY_TOLERANCE:
                negative.append({"step": row.get("step"), "field": field, "value": value})
        for field in PLANT_INVENTORY_FIELDS:
            value = plant.get(field)
            if _finite(value) and float(value) < -INVENTORY_TOLERANCE:
                negative.append(
                    {"step": row.get("step"), "field": "plant_sim." + field, "value": value}
                )
    if negative:
        return _check(
            "inventories_non_negative",
            FAILED,
            str(len(negative)) + " negative inventory readings",
            samples=negative[:10],
        )
    return _check("inventories_non_negative", PASSED)


# --------------------------------------------------------------------------- #
# 3. cumulative counters never run backwards
# --------------------------------------------------------------------------- #
def _totals_monotonic(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    names = sorted(
        {
            key
            for row in rows
            for key, value in _plant(row).items()
            if key.startswith("total_") and _finite(value)
        }
    )
    if not names:
        return _check("totals_monotonic", SKIPPED, "no cumulative totals in telemetry")

    regressions: List[Dict[str, Any]] = []
    previous: Dict[str, float] = {}
    for row in rows:
        plant = _plant(row)
        for name in names:
            value = plant.get(name)
            if not _finite(value):
                continue
            last = previous.get(name)
            if last is not None and float(value) < last - INVENTORY_TOLERANCE:
                regressions.append(
                    {"step": row.get("step"), "field": name, "from": last, "to": float(value)}
                )
            previous[name] = float(value)
    if regressions:
        return _check(
            "totals_monotonic",
            FAILED,
            str(len(regressions)) + " cumulative totals decreased",
            samples=regressions[:10],
        )
    return _check("totals_monotonic", PASSED, tracked=len(names))


# --------------------------------------------------------------------------- #
# 4-6. mass balance ledgers
#
# The opening inventory comes from the first telemetry row, not from the
# scenario's declared initial conditions: the run's own first measurement is
# what the run is accountable to.
# --------------------------------------------------------------------------- #
def _ledger(name: str, inflow: Sequence[float], outflow: Sequence[float]) -> Dict[str, Any]:
    residual = sum(inflow) - sum(outflow)
    if abs(residual) > LEDGER_TOLERANCE:
        return _check(
            name,
            FAILED,
            "residual " + repr(residual) + " exceeds tolerance " + repr(LEDGER_TOLERANCE),
            residual=residual,
            tolerance=LEDGER_TOLERANCE,
        )
    return _check(name, PASSED, residual=residual, tolerance=LEDGER_TOLERANCE)


def _ledger_or_skip(
    name: str,
    sources: Sequence[Tuple[Mapping[str, Any], str]],
    *,
    inflow_count: int,
) -> Dict[str, Any]:
    missing = [key for mapping, key in sources if not _finite(mapping.get(key))]
    if missing:
        return _check(name, SKIPPED, "missing ledger terms: " + ", ".join(missing))
    values = [float(mapping[key]) for mapping, key in sources]
    return _ledger(name, values[:inflow_count], values[inflow_count:])


def _carbon_ledger(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    first, last = rows[0], rows[-1]
    opening, closing = _plant(first), _plant(last)
    return _ledger_or_skip(
        "carbon_ledger",
        (
            (first, "co2_storage_kg"),
            (opening, "captured_co2_kg"),
            (closing, "total_co2_generated_kg"),
            (last, "co2_storage_kg"),
            (closing, "captured_co2_kg"),
            (closing, "total_co2_vented_kg"),
            (closing, "total_co2_delivered_kg"),
            (closing, "total_sabatier_co2_used_kg"),
        ),
        inflow_count=3,
    )


def _oxygen_ledger(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    first, last = rows[0], rows[-1]
    closing = _plant(last)
    return _ledger_or_skip(
        "oxygen_ledger",
        (
            (first, "o2_storage_kg"),
            (closing, "total_o2_generated_kg"),
            (last, "o2_storage_kg"),
            (closing, "total_o2_consumed_kg"),
            (closing, "total_o2_delivered_kg"),
        ),
        inflow_count=2,
    )


def _water_ledger(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    first, last = rows[0], rows[-1]
    opening, closing = _plant(first), _plant(last)
    return _ledger_or_skip(
        "water_ledger",
        (
            (first, "product_water_reserve_l"),
            (opening, "urine_buffer_l"),
            (first, "grey_water_collected_l"),
            (closing, "total_external_grey_water_submitted_l"),
            (closing, "total_water_regenerated_l"),
            (last, "product_water_reserve_l"),
            (closing, "urine_buffer_l"),
            (last, "grey_water_collected_l"),
            (closing, "total_unrecoverable_crew_water_l"),
            (closing, "total_wrs_brine_loss_l"),
            (closing, "total_electrolysis_water_kg"),
            (closing, "total_product_water_delivered_l"),
        ),
        inflow_count=5,
    )


# --------------------------------------------------------------------------- #
# 7. the reactions obey their own stoichiometry
# --------------------------------------------------------------------------- #
def _stoichiometric_residual(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    closing = _plant(rows[-1])
    o2 = closing.get("total_o2_generated_kg")
    water = closing.get("total_electrolysis_water_kg")
    if not _finite(o2) or not _finite(water):
        return _check(
            "stoichiometric_residual", SKIPPED, "electrolysis totals absent from telemetry"
        )

    residuals: Dict[str, float] = {
        "electrolysis_water_kg": float(water) - float(o2) * WATER_PER_O2,
    }
    # Sabatier is only checkable when the run recorded what it consumed and
    # vented; the hydrogen it used is what electrolysis made minus what escaped.
    co2_used = closing.get("total_sabatier_co2_used_kg")
    ch4 = closing.get("total_ch4_vented_kg")
    h2_vented = closing.get("total_h2_vented_kg")
    regenerated = closing.get("total_water_regenerated_l")
    if all(_finite(value) for value in (co2_used, ch4, h2_vented, regenerated)):
        h2_used = max(0.0, float(o2) * H2_PER_O2 - float(h2_vented))
        residuals["sabatier_co2_kg"] = float(co2_used) - h2_used * CO2_PER_H2
        residuals["sabatier_ch4_kg"] = float(ch4) - h2_used * CH4_PER_H2
        residuals["sabatier_water_l"] = float(regenerated) - h2_used * H2O_PER_H2

    scale = max(1.0, abs(float(o2)))
    violations = {
        key: value
        for key, value in residuals.items()
        if abs(value) > STOICHIOMETRY_TOLERANCE * scale
    }
    if violations:
        return _check(
            "stoichiometric_residual",
            FAILED,
            "reaction products do not match the consumed reactants",
            residuals=residuals,
            violations=violations,
        )
    return _check("stoichiometric_residual", PASSED, residuals=residuals)


# --------------------------------------------------------------------------- #
# 8-9. what the hardware did, against what it was allowed to do
# --------------------------------------------------------------------------- #
def _operation_rows(rows: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return [row for row in rows if "operations_this_step" in _plant(row)]


def _failure_state(row: Mapping[str, Any]) -> Mapping[str, Any]:
    plant = _plant(row)
    declared = plant.get("failure_state")
    if isinstance(declared, Mapping) and declared:
        return declared
    return {name: row.get(name + "_failure_enabled") for name in SUBSYSTEMS}


def _failure_quiescence(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    observed = _operation_rows(rows)
    if not observed:
        return _check(
            "failure_quiescence", SKIPPED, "telemetry carries no per-step operation record"
        )

    violations: List[Dict[str, Any]] = []
    for row in observed:
        failure = _failure_state(row)
        for operation in _plant(row).get("operations_this_step") or []:
            subsystem = str((operation or {}).get("subsystem") or "")
            if failure.get(subsystem) is True:
                violations.append({"step": row.get("step"), "subsystem": subsystem})
    if violations:
        return _check(
            "failure_quiescence",
            FAILED,
            "a failed subsystem processed work",
            samples=violations[:10],
        )
    return _check("failure_quiescence", PASSED, steps_observed=len(observed))


def _capacity_limits(capacity: Mapping[str, Any]) -> Optional[Dict[str, float]]:
    needed = _required_floats(
        capacity,
        (
            "ars_capacity_kg_day",
            "ars_operation_seconds",
            "ogs_max_o2_kg_day",
            "ogs_operation_seconds",
            "wrs_max_feed_l_per_operation",
        ),
    )
    if needed is None:
        return None
    return {
        "ars_per_operation_kg": (
            needed["ars_capacity_kg_day"] * needed["ars_operation_seconds"] / SECONDS_PER_DAY
        ),
        "ogs_per_operation_kg": (
            needed["ogs_max_o2_kg_day"] * needed["ogs_operation_seconds"] / SECONDS_PER_DAY
        ),
        "wrs_per_operation_l": needed["wrs_max_feed_l_per_operation"],
    }


def _capacity_violation(
    subsystem: str, operation: Mapping[str, Any], limits: Mapping[str, float]
) -> Optional[Dict[str, Any]]:
    if subsystem == "ars":
        if not _finite(operation.get("goal_scale")) or not _finite(operation.get("co2_removed_kg")):
            return {"missing": True}
        allowed = limits["ars_per_operation_kg"] * float(operation["goal_scale"])
        actual = float(operation["co2_removed_kg"])
    elif subsystem == "ogs":
        if not _finite(operation.get("o2_generated_kg")):
            return {"missing": True}
        allowed = limits["ogs_per_operation_kg"]
        actual = float(operation["o2_generated_kg"])
    elif subsystem == "wrs":
        urine = operation.get("urine_feed_l")
        grey = operation.get("grey_feed_l")
        if not _finite(urine) or not _finite(grey):
            return {"missing": True}
        allowed = limits["wrs_per_operation_l"]
        actual = float(urine) + float(grey)
    else:
        return None
    if actual > allowed + CAPACITY_TOLERANCE:
        return {"processed": actual, "allowed": allowed}
    return None


def _capacity_bounds(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    observed = [row for row in _operation_rows(rows) if _plant(row).get("installed_capacity")]
    if not observed:
        return _check(
            "capacity_bounds", SKIPPED, "telemetry carries no installed capacity snapshot"
        )

    violations: List[Dict[str, Any]] = []
    for row in observed:
        plant = _plant(row)
        limits = _capacity_limits(plant.get("installed_capacity") or {})
        if limits is None:
            return _check(
                "capacity_bounds",
                SKIPPED,
                "installed capacity snapshot is missing required terms",
            )
        for operation in plant.get("operations_this_step") or []:
            operation = operation or {}
            subsystem = str(operation.get("subsystem") or "")
            breach = _capacity_violation(subsystem, operation, limits)
            if breach is None:
                continue
            if breach.get("missing"):
                return _check(
                    "capacity_bounds",
                    SKIPPED,
                    "an operation is missing required capacity terms",
                )
            violations.append({"step": row.get("step"), "subsystem": subsystem, **breach})
    if violations:
        return _check(
            "capacity_bounds",
            FAILED,
            "a subsystem processed more than its installed capacity allows",
            samples=violations[:10],
        )
    return _check("capacity_bounds", PASSED, steps_observed=len(observed))


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def evaluate_physics(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Run the nine checks over telemetry rows and fold them into one status."""
    if not rows:
        checks = [_check(name, SKIPPED, "no telemetry rows") for name in CHECK_NAMES]
    else:
        checks = [
            _readings_present_and_finite(rows),
            _inventories_non_negative(rows),
            _totals_monotonic(rows),
            _carbon_ledger(rows),
            _oxygen_ledger(rows),
            _water_ledger(rows),
            _stoichiometric_residual(rows),
            _failure_quiescence(rows),
            _capacity_bounds(rows),
        ]

    statuses = [check["status"] for check in checks]
    if FAILED in statuses:
        status = FAILED
    elif SKIPPED in statuses:
        status = INCOMPLETE
    else:
        status = PASSED
    return {
        "status": status,
        # ``passed`` stays for readers that only ask the yes/no question.
        "passed": status == PASSED,
        "checks": checks,
        "failed": [check["name"] for check in checks if check["status"] == FAILED],
        "skipped": [check["name"] for check in checks if check["status"] == SKIPPED],
    }


def run_physics_gate(run_dir: Path) -> Dict[str, Any]:
    """Audit a completed run from its telemetry alone."""
    return evaluate_physics(read_telemetry(run_dir))


__all__ = [
    "CHECK_NAMES",
    "FAILED",
    "INCOMPLETE",
    "PASSED",
    "SKIPPED",
    "evaluate_physics",
    "read_telemetry",
    "run_physics_gate",
]
