"""Tests for StationSimulator ECLSS + EPS facade (EPS-3)."""

from environment.protocol import CommandKind, RecoveryCommand
from environment.scrubber.mock_eclss import MockEclssSimulator
from environment.scrubber.station_simulator import StationSimulator


def test_eps_boost_routes_through_bcdu():
    station = StationSimulator(MockEclssSimulator(initial_power_margin_w=-150.0))
    before = station.step()
    assert before.power_margin_w < 0.0

    result = station.apply_command(
        RecoveryCommand(kind=CommandKind.REQUEST_EPS_BOOST, value=150.0, issued_by="operator")
    )
    assert result.success
    assert "discharge armed" in result.message

    after = station.step()
    assert after.power_margin_w > before.power_margin_w
    assert after.eps_support_w == 150.0


def test_mock_eclss_rejects_eps_boost_without_facade():
    sim = MockEclssSimulator()
    result = sim.apply_command(
        RecoveryCommand(kind=CommandKind.REQUEST_EPS_BOOST, value=120.0)
    )
    assert not result.success
    assert "StationSimulator" in result.message
