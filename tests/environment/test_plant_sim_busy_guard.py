"""Operation duration / busy guard on the plant_sim backend (design doc §7.1)."""

from __future__ import annotations

import pytest

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


def test_busy_steps_follow_operation_seconds():
    b = _backend()
    # 4800 / 1200 = 4 steps for ARS; OGS and WRS run inside a single step.
    assert b.busy_steps("ars") == 4
    assert b.busy_steps("ogs") == 1
    assert b.busy_steps("wrs") == 1


def test_ars_rejected_while_busy_then_accepted_again():
    b = _backend()
    assert b.send_air_revitalisation_goal(ArsGoal()).success is True

    for expected_remaining in (3, 2, 1):
        b.advance_step()
        result = b.send_air_revitalisation_goal(ArsGoal())
        assert result.success is False
        assert result.details["reason"] == "subsystem_busy"
        assert result.details["subsystem"] == "ars"
        assert result.details["remaining_steps"] == expected_remaining
        assert result.details["operation_busy_steps"] == 4

    b.advance_step()  # step 4: the 80-minute operation is over
    assert b.send_air_revitalisation_goal(ArsGoal()).success is True


def test_busy_rejection_does_not_touch_state():
    b = _backend()
    b.send_air_revitalisation_goal(ArsGoal())
    b.advance_step()
    co2_before = b.model.state.cabin_co2_kg
    captured_before = b.model.state.captured_co2_kg
    assert b.send_air_revitalisation_goal(ArsGoal()).success is False
    assert b.model.state.cabin_co2_kg == pytest.approx(co2_before)
    assert b.model.state.captured_co2_kg == pytest.approx(captured_before)


def test_ogs_and_wrs_are_available_again_next_step():
    b = _backend()
    assert b.send_oxygen_generation_goal(OgsGoal(input_water_mass=0.1)).success is True
    assert b.send_water_recovery_goal(WrsGoal(urine_volume=1.0)).success is True
    # Same step: both are still occupied.
    assert b.send_oxygen_generation_goal(OgsGoal(input_water_mass=0.1)).success is False
    assert b.send_water_recovery_goal(WrsGoal(urine_volume=1.0)).success is False
    b.advance_step()
    assert b.send_oxygen_generation_goal(OgsGoal(input_water_mass=0.1)).success is True
    assert b.send_water_recovery_goal(WrsGoal(urine_volume=1.0)).success is True


def test_wrs_no_feed_does_not_occupy_the_subsystem():
    b = _backend(initial_urine_buffer_l=0.0, initial_grey_water_l=0.0)
    empty = b.send_water_recovery_goal(WrsGoal(urine_volume=1.0))
    assert empty.success is False
    assert empty.details["reason"] == "no_feed"
    b.model.state.urine_buffer_l = 5.0
    assert b.send_water_recovery_goal(WrsGoal(urine_volume=1.0)).success is True


def test_guard_can_be_disabled():
    b = _backend(operation_busy_guard_enabled=False)
    assert b.send_air_revitalisation_goal(ArsGoal()).success is True
    assert b.send_air_revitalisation_goal(ArsGoal()).success is True


def test_subsystem_failure_takes_precedence_over_busy():
    b = _backend()
    b.send_air_revitalisation_goal(ArsGoal())
    b.set_subsystem_failure("ars", True)
    result = b.send_air_revitalisation_goal(ArsGoal())
    assert result.success is False
    assert result.details.get("failed") is True


def test_telemetry_exposes_busy_countdown():
    b = _backend()
    b.send_air_revitalisation_goal(ArsGoal())
    topic = b.poll_telemetry().raw_topics["plant_sim"]
    assert topic["ars_busy_steps_remaining"] == 4
    b.advance_step()
    assert b.poll_telemetry().raw_topics["plant_sim"]["ars_busy_steps_remaining"] == 3
