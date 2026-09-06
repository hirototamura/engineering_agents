"""Telemetry-only physics gate (spec §12, §18.2).

Every case here builds telemetry rows by hand. That is the point of the gate:
it must reach its verdict from the measurement alone, so a test never has to
hand it a scenario config to make it work.
"""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from environment.ssos.eclss.plant_sim.stoichiometry import (
    CH4_PER_H2,
    CO2_PER_H2,
    H2O_PER_H2,
    H2_PER_O2,
    WATER_PER_O2,
)
from scenario.ssos_eclss_loop.physics_gate import (
    evaluate_physics,
    run_physics_gate,
)

CAPACITY = {
    "ars_capacity_kg_day": 4.5,
    "ogs_max_o2_kg_day": 9.25,
    "wrs_max_feed_l_per_operation": 10.0,
    "step_seconds": 1200.0,
    "ars_operation_seconds": 4800.0,
    "ogs_operation_seconds": 1200.0,
    "wrs_operation_seconds": 1200.0,
}


def _rows(**closing: Any) -> List[Dict[str, Any]]:
    """A two-row run that closes on every ledger, before any tampering."""
    o2_generated = 1.0
    h2_vented = 0.0
    h2_used = o2_generated * H2_PER_O2 - h2_vented

    opening_plant: Dict[str, Any] = {
        "captured_co2_kg": 0.0,
        "urine_buffer_l": 2.0,
        "crew_alive": 4,
        "installed_capacity": dict(CAPACITY),
        "failure_state": {"ars": False, "ogs": False, "wrs": False},
        "operations_this_step": [],
    }
    for name in (
        "total_co2_generated_kg",
        "total_co2_vented_kg",
        "total_co2_delivered_kg",
        "total_sabatier_co2_used_kg",
        "total_o2_generated_kg",
        "total_o2_consumed_kg",
        "total_o2_delivered_kg",
        "total_external_grey_water_submitted_l",
        "total_water_regenerated_l",
        "total_unrecoverable_crew_water_l",
        "total_wrs_brine_loss_l",
        "total_electrolysis_water_kg",
        "total_product_water_delivered_l",
        "total_ch4_vented_kg",
        "total_h2_vented_kg",
    ):
        opening_plant[name] = 0.0

    closing_plant = dict(opening_plant)
    closing_plant.update(
        {
            "captured_co2_kg": 0.5,
            "urine_buffer_l": 2.0,
            "total_o2_generated_kg": o2_generated,
            "total_electrolysis_water_kg": o2_generated * WATER_PER_O2,
            "total_sabatier_co2_used_kg": h2_used * CO2_PER_H2,
            "total_ch4_vented_kg": h2_used * CH4_PER_H2,
            "total_water_regenerated_l": h2_used * H2O_PER_H2,
            "operations_this_step": [
                # 4.5 kg/day over a 4800 s window is 0.25 kg at scale 1.0, so
                # removing 0.5 kg takes a goal worth 2.5 windows.
                {"subsystem": "ars", "co2_removed_kg": 0.5, "goal_scale": 2.5},
                {"subsystem": "ogs", "o2_generated_kg": 0.1},
                {"subsystem": "wrs", "urine_feed_l": 1.0, "grey_feed_l": 1.0},
            ],
        }
    )
    closing_plant.update(closing)

    # Opening cabin CO2 has to cover what ARS captures and what Sabatier eats,
    # or the run would close its ledger on a negative inventory.
    opening_co2 = 2.0
    opening = {
        "step": 0,
        "co2_storage_kg": opening_co2,
        "o2_storage_kg": 8.0,
        "product_water_reserve_l": 80.0,
        "grey_water_collected_l": 0.0,
        "ars_failure_enabled": False,
        "ogs_failure_enabled": False,
        "wrs_failure_enabled": False,
        "raw_topics": {"plant_sim": opening_plant},
    }
    # Close carbon: what leaves the cabin is what ARS captured plus what
    # Sabatier consumed, both of which the closing totals account for.
    closing_row = copy.deepcopy(opening)
    closing_row.update(
        {
            "step": 1,
            "co2_storage_kg": opening_co2
            - closing_plant["captured_co2_kg"]
            - closing_plant["total_sabatier_co2_used_kg"],
            "o2_storage_kg": 8.0 + o2_generated,
            "product_water_reserve_l": 80.0
            + closing_plant["total_water_regenerated_l"]
            - closing_plant["total_electrolysis_water_kg"],
            "raw_topics": {"plant_sim": closing_plant},
        }
    )
    return [opening, closing_row]


def _status(rows: List[Dict[str, Any]], name: str) -> str:
    checks = {check["name"]: check for check in evaluate_physics(rows)["checks"]}
    return checks[name]["status"]


def test_a_closing_run_passes_every_check():
    assert evaluate_physics(_rows())["status"] == "passed"


def test_a_real_run_passes_from_its_telemetry_alone():
    from scenario.ssos_eclss_loop.scenario_run import SsosEclssLoopScenario

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = SsosEclssLoopScenario().run(
            output_dir=Path(tmp) / "run",
            overrides={
                "simulation": {"steps": 12},
                "backend": {"kind": "plant_sim"},
                "agents": {"actor": {"mode": "labeled_rule_base"}, "design": {"mode": "none"}},
            },
            recreate_output=True,
        )
        assert run_physics_gate(run_dir)["status"] == "passed"


def test_no_telemetry_is_incomplete_not_passed():
    result = evaluate_physics([])
    assert result["status"] == "incomplete"
    assert result["passed"] is False
    assert len(result["skipped"]) == 10


def test_missing_audit_fields_are_incomplete_not_passed():
    """A run recorded before the audit fields existed must not read as clean."""
    rows = _rows()
    for row in rows:
        plant = row["raw_topics"]["plant_sim"]
        plant.pop("installed_capacity")
        plant.pop("operations_this_step")

    result = evaluate_physics(rows)
    assert result["status"] == "incomplete"
    assert set(result["skipped"]) == {
        "failure_quiescence",
        "capacity_bounds",
        "operational_physical_bounds",
    }
    assert not result["failed"]


def test_broken_mass_balance_fails():
    rows = _rows()
    rows[-1]["o2_storage_kg"] += 5.0

    result = evaluate_physics(rows)
    assert result["status"] == "failed"
    assert result["failed"] == ["oxygen_ledger"]


def test_non_finite_reading_fails():
    rows = _rows()
    rows[-1]["co2_storage_kg"] = None
    assert _status(rows, "readings_present_and_finite") == "failed"


def test_negative_inventory_fails():
    rows = _rows()
    rows[-1]["product_water_reserve_l"] = -1.0
    assert _status(rows, "inventories_non_negative") == "failed"


def test_cumulative_total_running_backwards_fails():
    rows = _rows()
    rows[0]["raw_topics"]["plant_sim"]["total_co2_vented_kg"] = 5.0
    assert _status(rows, "totals_monotonic") == "failed"


def test_stoichiometry_violation_fails():
    """Electrolysis that made oxygen out of less water than the reaction needs."""
    rows = _rows()
    rows[-1]["raw_topics"]["plant_sim"]["total_electrolysis_water_kg"] *= 0.5
    assert _status(rows, "stoichiometric_residual") == "failed"


def test_failed_subsystem_that_processed_work_fails():
    rows = _rows()
    rows[-1]["raw_topics"]["plant_sim"]["failure_state"] = {
        "ars": True,
        "ogs": False,
        "wrs": False,
    }
    assert _status(rows, "failure_quiescence") == "failed"


def test_processing_beyond_installed_capacity_fails():
    rows = _rows()
    operations = rows[-1]["raw_topics"]["plant_sim"]["operations_this_step"]
    # 9.25 kg/day over a 1200 s window is ~0.128 kg of O2, so 5 kg is impossible.
    operations[1]["o2_generated_kg"] = 5.0
    assert _status(rows, "capacity_bounds") == "failed"


def test_capacity_bound_follows_the_installed_hardware():
    """The same operation is legal once the hardware that could do it is fitted."""
    rows = _rows()
    operations = rows[-1]["raw_topics"]["plant_sim"]["operations_this_step"]
    operations[1]["o2_generated_kg"] = 5.0
    assert _status(rows, "capacity_bounds") == "failed"

    for row in rows:
        row["raw_topics"]["plant_sim"]["installed_capacity"]["ogs_max_o2_kg_day"] = 400.0
    assert _status(rows, "capacity_bounds") == "passed"


def test_ars_bound_scales_with_the_goal():
    rows = _rows()
    operations = rows[-1]["raw_topics"]["plant_sim"]["operations_this_step"]
    # 4.5 kg/day over a 4800 s window is 0.25 kg at scale 1.0, so the fixture's
    # scale of 2.5 allows 0.625 kg and no more.
    operations[0]["co2_removed_kg"] = 0.7
    assert _status(rows, "capacity_bounds") == "failed"

    operations[0]["goal_scale"] = 4.0
    assert _status(rows, "capacity_bounds") == "passed"


def test_negative_processed_amount_fails_operational_bounds():
    rows = _rows()
    operations = rows[-1]["raw_topics"]["plant_sim"]["operations_this_step"]
    operations[0]["co2_removed_kg"] = -0.1
    assert _status(rows, "operational_physical_bounds") == "failed"


def test_merge_keeps_scorecard_only_checks():
    from scenario.ssos_eclss_loop.physics_gate import merge_physics_gates

    telemetry = evaluate_physics(_rows())
    scorecard = {
        "passed": True,
        "checks": [
            {
                "name": "mass_balance_ledgers",
                "passed": True,
                "residuals": {"o2_kg": 0.0, "co2_kg": 0.0, "water_l": 0.0},
            },
            {
                "name": "operational_physical_bounds",
                "passed": True,
                "details": [],
            },
        ],
    }
    merged = merge_physics_gates(scorecard, telemetry)
    names = [check["name"] for check in merged["checks"]]
    assert "mass_balance_ledgers" in names
    assert names.count("operational_physical_bounds") == 2
    assert merged["scorecard_checks_kept"] == [
        "mass_balance_ledgers",
        "operational_physical_bounds",
    ]
    assert merged["status"] == "passed"


def test_merge_does_not_overwrite_a_failing_scorecard_check():
    from scenario.ssos_eclss_loop.physics_gate import merge_physics_gates, physics_gate_index

    telemetry = evaluate_physics(_rows())
    assert _status(_rows(), "operational_physical_bounds") == "passed"
    scorecard = {
        "passed": False,
        "checks": [
            {
                "name": "operational_physical_bounds",
                "passed": False,
                "details": [{"step": 1, "kind": "air_revitalisation"}],
            }
        ],
    }
    merged = merge_physics_gates(scorecard, telemetry)
    assert merged["status"] == "failed"
    assert merged["passed"] is False
    assert "operational_physical_bounds" in merged["failed"]
    assert physics_gate_index("plant_sim", "invalid", merged) is False


def test_physics_gate_index_is_null_when_the_gate_did_not_run():
    from scenario.ssos_eclss_loop.physics_gate import physics_gate_index

    gate = {"passed": False, "status": "incomplete"}
    assert physics_gate_index("mock", "not_applicable", gate) is None
    assert physics_gate_index("plant_sim", "not_applicable", gate) is None
    assert physics_gate_index("plant_sim", "scored", {"passed": True}) is True
    assert physics_gate_index("plant_sim", "invalid", {"passed": False}) is False
