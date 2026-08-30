"""Telemetry carries what an independent physics audit needs (spec §13).

The physics gate judges a run from ``telemetry.jsonl`` alone. Anything it must
check against -- the installed envelope and what each subsystem actually
processed -- therefore has to travel in the telemetry rather than being looked
up in the scenario config afterwards.
"""

from __future__ import annotations

from environment.ssos.eclss.plant_sim.backend import PlantSimEclssBackend
from environment.ssos.eclss.plant_sim.config import PlantSimConfig
from environment.ssos.eclss.types import ArsGoal, OgsGoal, WrsGoal


def _backend(**overrides) -> PlantSimEclssBackend:
    base = dict(
        crew_size=4,
        initial_cabin_co2_kg=50.0,
        initial_o2_kg=5.0,
        initial_product_water_l=200.0,
        initial_urine_buffer_l=20.0,
        initial_grey_water_l=10.0,
    )
    base.update(overrides)
    return PlantSimEclssBackend(PlantSimConfig(**base))


def _topic(backend: PlantSimEclssBackend) -> dict:
    return backend.poll_telemetry().raw_topics["plant_sim"]


def test_installed_capacity_snapshot_matches_the_configured_hardware():
    backend = _backend(ars_capacity_kg_day=23.92, ogs_max_o2_kg_day=48.3)
    capacity = _topic(backend)["installed_capacity"]

    assert capacity["ars_capacity_kg_day"] == 23.92
    assert capacity["ogs_max_o2_kg_day"] == 48.3
    assert capacity["wrs_max_feed_l_per_operation"] == 10.0
    # The cadence matters as much as the nameplate: an ARS that occupies four
    # steps cannot deliver its daily figure once per step.
    assert capacity["step_seconds"] == 1200.0
    assert capacity["ars_operation_seconds"] == 4800.0


def test_processed_quantity_is_reported_for_an_operation_that_ran():
    backend = _backend()
    assert backend.send_air_revitalisation_goal(ArsGoal()).success is True

    operations = _topic(backend)["operations_this_step"]
    assert [item["subsystem"] for item in operations] == ["ars"]
    assert operations[0]["co2_removed_kg"] > 0.0


def test_polling_twice_in_one_step_reports_the_same_operations():
    """A step is polled before and after the actions; neither poll consumes it."""
    backend = _backend()
    backend.send_air_revitalisation_goal(ArsGoal())

    first = _topic(backend)["operations_this_step"]
    second = _topic(backend)["operations_this_step"]
    assert first == second and len(first) == 1


def test_operations_are_cleared_at_the_step_boundary():
    backend = _backend()
    backend.send_air_revitalisation_goal(ArsGoal())
    assert _topic(backend)["operations_this_step"]

    backend.advance_step()
    assert _topic(backend)["operations_this_step"] == []


def test_a_rejected_command_processes_nothing():
    backend = _backend()
    assert backend.send_air_revitalisation_goal(ArsGoal()).success is True
    backend.advance_step()

    # ARS occupies four steps, so this one is refused and must not appear as
    # processed work -- otherwise the audit would credit an operation that the
    # hardware never performed.
    assert backend.send_air_revitalisation_goal(ArsGoal()).success is False
    assert _topic(backend)["operations_this_step"] == []


def test_ogs_and_wrs_report_their_own_quantities():
    backend = _backend()
    assert backend.send_oxygen_generation_goal(OgsGoal(input_water_mass=0.15)).success is True
    assert backend.send_water_recovery_goal(WrsGoal(urine_volume=5.0)).success is True

    operations = {item["subsystem"]: item for item in _topic(backend)["operations_this_step"]}
    assert operations["ogs"]["o2_generated_kg"] > 0.0
    assert operations["wrs"]["recovered_water_l"] > 0.0


def test_failure_state_travels_with_the_measurement():
    backend = _backend()
    backend.set_subsystem_failure("ars", True)
    assert _topic(backend)["failure_state"] == {"ars": True, "ogs": False, "wrs": False}
