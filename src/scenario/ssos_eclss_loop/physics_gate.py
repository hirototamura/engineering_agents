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
from typing import Any, Dict, List, Mapping, Optional, Sequence

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
    "operational_physical_bounds",
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


def _carbon_ledger(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    first, last = rows[0], rows[-1]
    opening, closing = _plant(first), _plant(last)
    inflow = (
        _number(first.get("co2_storage_kg")),
        _number(opening.get("captured_co2_kg")),
        _number(closing.get("total_co2_generated_kg")),
    )
    outflow = (
        _number(last.get("co2_storage_kg")),
        _number(closing.get("captured_co2_kg")),
        _number(closing.get("total_co2_vented_kg")),
        _number(closing.get("total_co2_delivered_kg")),
        _number(closing.get("total_sabatier_co2_used_kg")),
    )
    return _ledger("carbon_ledger", inflow, outflow)


def _oxygen_ledger(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    first, last = rows[0], rows[-1]
    closing = _plant(last)
    inflow = (
        _number(first.get("o2_storage_kg")),
        _number(closing.get("total_o2_generated_kg")),
    )
    outflow = (
        _number(last.get("o2_storage_kg")),
        _number(closing.get("total_o2_consumed_kg")),
        _number(closing.get("total_o2_delivered_kg")),
    )
    return _ledger("oxygen_ledger", inflow, outflow)


def _water_ledger(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    first, last = rows[0], rows[-1]
    opening, closing = _plant(first), _plant(last)
    inflow = (
        _number(first.get("product_water_reserve_l")),
        _number(opening.get("urine_buffer_l")),
        _number(first.get("grey_water_collected_l")),
        _number(closing.get("total_external_grey_water_submitted_l")),
        _number(closing.get("total_water_regenerated_l")),
    )
    outflow = (
        _number(last.get("product_water_reserve_l")),
        _number(closing.get("urine_buffer_l")),
        _number(last.get("grey_water_collected_l")),
        _number(closing.get("total_unrecoverable_crew_water_l")),
        _number(closing.get("total_wrs_brine_loss_l")),
        _number(closing.get("total_electrolysis_water_kg")),
        _number(closing.get("total_product_water_delivered_l")),
    )
    return _ledger("water_ledger", inflow, outflow)


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


def _capacity_limits(capacity: Mapping[str, Any]) -> Dict[str, float]:
    return {
        # The nameplate is a daily rate; one operation only gets its own window.
        "ars_per_operation_kg": _number(capacity.get("ars_capacity_kg_day"))
        * _number(capacity.get("ars_operation_seconds"))
        / SECONDS_PER_DAY,
        "ogs_per_operation_kg": _number(capacity.get("ogs_max_o2_kg_day"))
        * _number(capacity.get("ogs_operation_seconds"))
        / SECONDS_PER_DAY,
        "wrs_per_operation_l": _number(capacity.get("wrs_max_feed_l_per_operation")),
    }


def _capacity_violation(
    subsystem: str, operation: Mapping[str, Any], limits: Mapping[str, float]
) -> Optional[Dict[str, float]]:
    if subsystem == "ars":
        # The goal scales the window: a larger goal buys proportionally more.
        allowed = limits["ars_per_operation_kg"] * _number(operation.get("goal_scale"))
        actual = _number(operation.get("co2_removed_kg"))
    elif subsystem == "ogs":
        allowed = limits["ogs_per_operation_kg"]
        actual = _number(operation.get("o2_generated_kg"))
    elif subsystem == "wrs":
        allowed = limits["wrs_per_operation_l"]
        actual = _number(operation.get("urine_feed_l")) + _number(operation.get("grey_feed_l"))
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
        for operation in plant.get("operations_this_step") or []:
            operation = operation or {}
            subsystem = str(operation.get("subsystem") or "")
            breach = _capacity_violation(subsystem, operation, limits)
            if breach is not None:
                violations.append({"step": row.get("step"), "subsystem": subsystem, **breach})
    if violations:
        return _check(
            "capacity_bounds",
            FAILED,
            "a subsystem processed more than its installed capacity allows",
            samples=violations[:10],
        )
    return _check("capacity_bounds", PASSED, steps_observed=len(observed))


def _operational_physical_bounds(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Sign and finiteness of processed amounts — the scorecard gate's
    ``operational_physical_bounds`` check, read from telemetry operations
    rather than events so this gate stays independently auditable.
    """
    observed = _operation_rows(rows)
    if not observed:
        return _check(
            "operational_physical_bounds",
            SKIPPED,
            "telemetry carries no per-step operation record",
        )

    violations: List[Dict[str, Any]] = []
    for row in observed:
        for operation in _plant(row).get("operations_this_step") or []:
            operation = operation or {}
            subsystem = str(operation.get("subsystem") or "")
            fields: tuple[str, ...]
            if subsystem == "ars":
                fields = ("co2_removed_kg",)
            elif subsystem == "ogs":
                fields = ("processed_water_kg", "o2_generated_kg")
            elif subsystem == "wrs":
                fields = ("recovered_water_l",)
            else:
                continue
            for field in fields:
                value = operation.get(field)
                if value is None:
                    continue
                if not _finite(value) or float(value) < -INVENTORY_TOLERANCE:
                    violations.append(
                        {
                            "step": row.get("step"),
                            "subsystem": subsystem,
                            "field": field,
                            "value": value,
                        }
                    )
    if violations:
        return _check(
            "operational_physical_bounds",
            FAILED,
            "an operation reported a non-finite or negative processed amount",
            samples=violations[:10],
        )
    return _check("operational_physical_bounds", PASSED, steps_observed=len(observed))


def _check_failed(check: Mapping[str, Any]) -> bool:
    if "status" in check:
        return check["status"] == FAILED
    return check.get("passed") is False


def _check_skipped(check: Mapping[str, Any]) -> bool:
    if check.get("status") == SKIPPED:
        return True
    return "status" not in check and check.get("passed") is None


def merge_physics_gates(
    scorecard: Mapping[str, Any], telemetry: Mapping[str, Any]
) -> Dict[str, Any]:
    """Keep the scorecard gate's checks and add any the telemetry gate lacks.

    The telemetry-only audit does not overwrite the evaluator's own gate.
    Checks that exist only on the older scorecard gate (different names or
    event-based formulas) are appended so both verdicts stay visible.
    """
    telemetry_checks = list(telemetry.get("checks") or [])
    seen = {check.get("name") for check in telemetry_checks}
    extras = [
        dict(check)
        for check in (scorecard.get("checks") or [])
        if check.get("name") not in seen
    ]
    checks = telemetry_checks + extras
    failed = [str(check.get("name")) for check in checks if _check_failed(check)]
    skipped = [str(check.get("name")) for check in checks if _check_skipped(check)]
    if failed:
        status = FAILED
    elif skipped:
        status = INCOMPLETE
    elif checks:
        status = PASSED
    else:
        status = INCOMPLETE
    return {
        "status": status,
        "passed": status == PASSED,
        "checks": checks,
        "failed": failed,
        "skipped": skipped,
        "scorecard_checks_kept": [str(check.get("name")) for check in extras],
    }


def physics_gate_index(backend: str, evaluation_status: str, gate: Mapping[str, Any]) -> Optional[bool]:
    """``True``/``False`` only when the gate ran on a physics-bearing run.

    Mock / ros2 / evaluation-disabled runs never execute the audit. Reporting
    ``false`` there would collapse "not run" into "failed".
    """
    if backend != "plant_sim" or evaluation_status == "not_applicable":
        return None
    return bool(gate.get("passed"))


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def evaluate_physics(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Run the checks over telemetry rows and fold them into one status."""
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
            _operational_physical_bounds(rows),
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
    "merge_physics_gates",
    "physics_gate_index",
    "read_telemetry",
    "run_physics_gate",
]
