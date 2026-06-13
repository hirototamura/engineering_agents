"""Contract tests for MockEclssBackend (Phase 1b)."""

import pytest

from environment.ssos.eclss_backend import EclssBackend
from environment.ssos.eclss_types import ArsGoal, OgsGoal, WrsGoal
from environment.ssos.mock_eclss_backend import MockEclssBackend


def test_mock_backend_satisfies_protocol():
    backend = MockEclssBackend()
    assert isinstance(backend, EclssBackend)


def test_mock_poll_telemetry_returns_defaults():
    snap = MockEclssBackend().poll_telemetry()
    assert snap.co2_storage_kg == 1800.0
    assert snap.o2_storage_kg == 500.0
    assert snap.product_water_reserve_l == 100.0


def test_mock_ars_and_ogs_goals():
    backend = MockEclssBackend()
    ars = backend.send_air_revitalisation_goal(ArsGoal(initial_co2_mass=900.0))
    ogs = backend.send_oxygen_generation_goal(OgsGoal(input_water_mass=10.0))
    assert ars.success
    assert ogs.success
    assert backend.last_ars_goal.initial_co2_mass == 900.0
    assert backend.last_ogs_goal.input_water_mass == 10.0


def test_mock_o2_and_co2_services():
    backend = MockEclssBackend()
    o2 = backend.request_o2(250.0)
    co2 = backend.request_co2(100.0)
    assert o2.success and o2.response_value == 250.0
    assert co2.success and co2.response_value == 100.0


def test_mock_set_subsystem_failure():
    backend = MockEclssBackend()
    backend.set_subsystem_failure("ars", True)
    snap = backend.poll_telemetry()
    assert snap.ars_failure_enabled is True


def test_mock_wrs_methods_raise_not_implemented():
    backend = MockEclssBackend()
    with pytest.raises(NotImplementedError):
        backend.send_water_recovery_goal(WrsGoal())
    with pytest.raises(NotImplementedError):
        backend.request_product_water(1.0)
    with pytest.raises(NotImplementedError):
        backend.submit_grey_water(1.0)
