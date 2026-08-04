"""Coupled SARJ + BCDU stack for mock EPS simulation (EPS-2); wired to ECLSS in EPS-3."""

from __future__ import annotations

from typing import Optional, Tuple

from environment.scrubber.eps.types import BcduStatus, DischargeResult, SarjReading
from environment.scrubber.eps.mock.bcdu import MockBcdu
from environment.scrubber.eps.mock.sarj import MockSarj


class EpsStack:
    """Thin EPS subsystem: SARJ publishes solar voltage, BCDU manages discharge."""

    def __init__(
        self,
        sarj: Optional[MockSarj] = None,
        bcdu: Optional[MockBcdu] = None,
    ):
        self.sarj = sarj or MockSarj()
        self.bcdu = bcdu or MockBcdu()

    def step(self) -> Tuple[SarjReading, BcduStatus]:
        solar = self.sarj.step()
        self.bcdu.update_solar(solar.solar_voltage_v)
        status = self.bcdu.step()
        return solar, status

    def request_discharge(self, support_w: float, duration_steps: int) -> DischargeResult:
        return self.bcdu.request_discharge(support_w, duration_steps)

    def consume_scheduled_support(self) -> float:
        return self.bcdu.consume_scheduled_support()
