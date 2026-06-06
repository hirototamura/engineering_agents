"""Mock BCDU — charge/discharge controller (space_station_eps inspired)."""

from __future__ import annotations

from typing import List, Optional

from environment.ssos.eps_types import BcduMode, BcduStatus, DischargeResult, EpsDiagnostics


class MockBcdu:
    """
    Simplified battery charge/discharge unit.

    Uses solar voltage to choose charge vs discharge bias; arms discharge
    support watts for downstream ECLSS (consumed in EPS-3 facade).
    """

    def __init__(
        self,
        bus_voltage_v: float = 110.0,
        regulation_voltage_v: float = 120.0,
        min_safe_voltage_v: float = 70.0,
        max_safe_voltage_v: float = 120.0,
        solar_charge_threshold_v: float = 90.0,
        max_discharge_w: float = 500.0,
    ):
        self.bus_voltage_v = bus_voltage_v
        self.regulation_voltage_v = regulation_voltage_v
        self.min_safe_voltage_v = min_safe_voltage_v
        self.max_safe_voltage_v = max_safe_voltage_v
        self.solar_charge_threshold_v = solar_charge_threshold_v
        self.max_discharge_w = max_discharge_w
        self.step_count = 0
        self.solar_voltage_v = 0.0
        self.mode = BcduMode.IDLE
        self.fault = False
        self.fault_message = ""
        self.support_w = 0.0
        self.support_steps_remaining = 0
        self._diagnostics: List[EpsDiagnostics] = []

    def update_solar(self, solar_voltage_v: float) -> None:
        self.solar_voltage_v = solar_voltage_v
        if self.fault:
            self.mode = BcduMode.FAULT
            return
        if self.support_steps_remaining > 0:
            self.mode = BcduMode.DISCHARGING
        elif solar_voltage_v >= self.solar_charge_threshold_v:
            self.mode = BcduMode.CHARGING
        else:
            self.mode = BcduMode.IDLE

    def step(self) -> BcduStatus:
        self.step_count += 1
        if self.fault:
            self.mode = BcduMode.FAULT
        elif self.support_steps_remaining > 0:
            self.mode = BcduMode.DISCHARGING
            self.support_steps_remaining -= 1
            if self.support_steps_remaining == 0:
                self.support_w = 0.0
                if self.solar_voltage_v >= self.solar_charge_threshold_v:
                    self.mode = BcduMode.CHARGING
                else:
                    self.mode = BcduMode.IDLE
        elif self.solar_voltage_v >= self.solar_charge_threshold_v:
            self.mode = BcduMode.CHARGING
            self.bus_voltage_v = min(
                self.max_safe_voltage_v,
                self.bus_voltage_v + 0.5,
            )
        else:
            self.mode = BcduMode.IDLE

        current_draw = 0.0
        if self.mode == BcduMode.DISCHARGING and self.support_w > 0:
            current_draw = self.support_w / max(self.bus_voltage_v, 1.0)

        return self._status(current_draw_a=current_draw)

    def request_discharge(self, support_w: float, duration_steps: int) -> DischargeResult:
        if self.fault:
            return DischargeResult(
                success=False,
                message=f"BCDU fault latched: {self.fault_message}",
                status=self._status(),
            )
        if not (0.0 < support_w <= self.max_discharge_w):
            return DischargeResult(
                success=False,
                message=f"discharge watts out of range: {support_w}",
                status=self._status(),
            )
        if duration_steps < 1:
            return DischargeResult(
                success=False,
                message=f"duration_steps must be >= 1, got {duration_steps}",
                status=self._status(),
            )
        if not (self.min_safe_voltage_v <= self.bus_voltage_v <= self.max_safe_voltage_v):
            self._enter_fault(f"bus voltage {self.bus_voltage_v:.1f} V outside safe band")
            return DischargeResult(
                success=False,
                message=self.fault_message,
                status=self._status(),
            )

        self.support_w = float(support_w)
        self.support_steps_remaining = int(duration_steps)
        self.mode = BcduMode.DISCHARGING
        msg = (
            f"discharge armed {self.support_w:.1f} W "
            f"for {self.support_steps_remaining} steps"
        )
        self._diagnostics.append(
            EpsDiagnostics(
                step=self.step_count,
                component="bcdu",
                level="OK",
                message=msg,
                details={"solar_voltage_v": self.solar_voltage_v},
            )
        )
        return DischargeResult(success=True, message=msg, status=self._status())

    def consume_scheduled_support(self) -> float:
        """Watts to deliver to ECLSS bus this step (0 if not discharging)."""
        if self.support_steps_remaining > 0 and self.support_w > 0:
            return self.support_w
        return 0.0

    def get_diagnostics(self) -> List[EpsDiagnostics]:
        return list(self._diagnostics)

    def _enter_fault(self, message: str) -> None:
        self.fault = True
        self.fault_message = message
        self.mode = BcduMode.FAULT
        self.support_w = 0.0
        self.support_steps_remaining = 0
        self._diagnostics.append(
            EpsDiagnostics(
                step=self.step_count,
                component="bcdu",
                level="ERROR",
                message=message,
                details={"bus_voltage_v": self.bus_voltage_v},
            )
        )

    def _status(self, current_draw_a: float = 0.0) -> BcduStatus:
        return BcduStatus(
            step=self.step_count,
            mode=self.mode,
            bus_voltage_v=self.bus_voltage_v,
            regulation_voltage_v=self.regulation_voltage_v,
            current_draw_a=current_draw_a,
            fault=self.fault,
            fault_message=self.fault_message,
            support_w=self.support_w,
            support_steps_remaining=self.support_steps_remaining,
        )
