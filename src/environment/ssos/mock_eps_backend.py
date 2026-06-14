"""In-memory EpsBackend backed by mock SARJ + BCDU (EPS-2 stack)."""

from __future__ import annotations

from typing import Optional

from environment.ssos.eps_stack import EpsStack
from environment.ssos.eps_types import BcduMode, BcduStatus, DischargeResult, SarjReading
from environment.ssos.mock_bcdu import MockBcdu
from environment.ssos.mock_sarj import MockSarj


class MockEpsBackend:
    """Wraps ``EpsStack`` to satisfy ``EpsBackend`` without ROS or SSOS."""

    def __init__(self, stack: Optional[EpsStack] = None) -> None:
        self._stack = stack or EpsStack()

    @property
    def stack(self) -> EpsStack:
        return self._stack

    @property
    def support_w(self) -> float:
        return self._stack.bcdu.support_w

    @property
    def support_steps_remaining(self) -> int:
        return self._stack.bcdu.support_steps_remaining

    @property
    def bcdu_mode(self) -> BcduMode:
        return self._stack.bcdu.mode

    def poll_solar(self) -> SarjReading:
        solar = self._stack.sarj.step()
        self._stack.bcdu.update_solar(solar.solar_voltage_v)
        return solar

    def poll_bcdu(self) -> BcduStatus:
        bcdu = self._stack.bcdu
        current_draw = 0.0
        if bcdu.support_steps_remaining > 0 and bcdu.support_w > 0:
            current_draw = bcdu.support_w / max(bcdu.bus_voltage_v, 1.0)
        return BcduStatus(
            step=bcdu.step_count,
            mode=bcdu.mode,
            bus_voltage_v=bcdu.bus_voltage_v,
            regulation_voltage_v=bcdu.regulation_voltage_v,
            current_draw_a=current_draw,
            fault=bcdu.fault,
            fault_message=bcdu.fault_message,
            support_w=bcdu.support_w,
            support_steps_remaining=bcdu.support_steps_remaining,
        )

    def tick_bcdu(self) -> BcduStatus:
        return self._stack.bcdu.step()

    def request_discharge(self, support_w: float, duration_steps: int) -> DischargeResult:
        return self._stack.request_discharge(support_w, duration_steps)

    def consume_scheduled_support(self) -> float:
        return self._stack.consume_scheduled_support()


def build_mock_eps_backend(
    *,
    beta_angle_deg: float = 45.0,
    eclipse_window: Optional[tuple[int, int]] = None,
) -> MockEpsBackend:
    sarj = MockSarj(
        beta_angle_deg=beta_angle_deg,
        eclipse_window=eclipse_window,
    )
    return MockEpsBackend(EpsStack(sarj=sarj))
