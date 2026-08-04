"""Contract tests for MockEpsBackend (Phase 3)."""

from environment.scrubber.eps.backend import EpsBackend
from environment.scrubber.eps.types import BcduMode
from environment.scrubber.eps.mock.backend import MockEpsBackend, build_mock_eps_backend


def test_mock_eps_backend_satisfies_protocol():
    assert isinstance(MockEpsBackend(), EpsBackend)


def test_mock_eps_backend_discharge_flow():
    backend = build_mock_eps_backend(beta_angle_deg=60.0)
    backend.poll_solar()
    result = backend.request_discharge(100.0, 2)
    assert result.success
    support = backend.consume_scheduled_support()
    assert support == 100.0
    backend.tick_bcdu()
    assert backend.support_steps_remaining == 1


def test_mock_eps_backend_tick_decrements_duration():
    backend = build_mock_eps_backend(beta_angle_deg=60.0)
    backend.poll_solar()
    backend.request_discharge(80.0, 2)
    backend.consume_scheduled_support()
    backend.tick_bcdu()
    backend.consume_scheduled_support()
    backend.tick_bcdu()
    backend.consume_scheduled_support()
    backend.tick_bcdu()
    assert backend.support_steps_remaining == 0
    assert backend.consume_scheduled_support() == 0.0
