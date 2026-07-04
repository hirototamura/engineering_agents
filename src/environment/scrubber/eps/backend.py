"""EpsBackend protocol — thin interface for EPS telemetry and discharge ops."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from environment.scrubber.eps.types import BcduMode, BcduStatus, DischargeResult, SarjReading


@runtime_checkable
class EpsBackend(Protocol):
    """Backend for EPS closed-loop ops (mock SARJ/BCDU or SSOS ROS 2 bridge)."""

    def poll_solar(self) -> SarjReading: ...

    def poll_bcdu(self) -> BcduStatus: ...

    def tick_bcdu(self) -> BcduStatus: ...

    def request_discharge(self, support_w: float, duration_steps: int) -> DischargeResult: ...

    def consume_scheduled_support(self) -> float: ...

    @property
    def support_w(self) -> float: ...

    @property
    def support_steps_remaining(self) -> int: ...

    @property
    def bcdu_mode(self) -> BcduMode: ...
