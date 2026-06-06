"""Tests for mock EPS (SARJ + BCDU) — EPS-2."""

from environment.ssos.eps_stack import EpsStack
from environment.ssos.eps_types import BcduMode
from environment.ssos.mock_bcdu import MockBcdu
from environment.ssos.mock_sarj import MockSarj


def test_sarj_eclipse_produces_low_solar_voltage():
    sarj = MockSarj(beta_angle_deg=10.0, eclipse_window=(5, 8), eclipse_voltage_v=55.0)
    readings = [sarj.step() for _ in range(10)]
    assert readings[4].in_eclipse
    assert readings[4].solar_voltage_v == 55.0
    assert sarj.is_sunlight_low(readings[4].solar_voltage_v)
    assert readings[9].solar_voltage_v > 90.0


def test_bcdu_charges_when_solar_voltage_high():
    bcdu = MockBcdu(bus_voltage_v=100.0)
    bcdu.update_solar(140.0)
    status = bcdu.step()
    assert status.mode == BcduMode.CHARGING
    assert status.bus_voltage_v > 100.0


def test_bcdu_discharge_request_arms_support():
    bcdu = MockBcdu()
    bcdu.update_solar(60.0)
    result = bcdu.request_discharge(support_w=120.0, duration_steps=3)
    assert result.success
    assert "discharge armed" in result.message
    assert bcdu.support_w == 120.0
    assert bcdu.support_steps_remaining == 3


def test_bcdu_rejects_discharge_when_bus_voltage_unsafe():
    bcdu = MockBcdu(bus_voltage_v=65.0)
    result = bcdu.request_discharge(support_w=100.0, duration_steps=2)
    assert not result.success
    assert bcdu.fault
    assert bcdu.mode == BcduMode.FAULT


def test_bcdu_consumes_support_over_duration():
    stack = EpsStack(sarj=MockSarj(beta_angle_deg=60.0), bcdu=MockBcdu())
    stack.step()
    stack.request_discharge(80.0, 2)
    w1 = stack.consume_scheduled_support()
    stack.step()
    w2 = stack.consume_scheduled_support()
    stack.step()
    w3 = stack.consume_scheduled_support()
    assert w1 == 80.0
    assert w2 == 80.0
    assert w3 == 0.0


def test_eps_stack_sarj_feeds_bcdu_mode():
    stack = EpsStack(
        sarj=MockSarj(beta_angle_deg=80.0, eclipse_window=(2, 4), eclipse_voltage_v=50.0),
    )
    solar, status = stack.step()
    assert solar.step == 1
    stack.step()
    solar2, status2 = stack.step()
    assert solar2.in_eclipse
    assert status2.mode in {BcduMode.IDLE, BcduMode.DISCHARGING}
