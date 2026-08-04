"""Mock SARJ — solar array tracking voltage estimate (space_station_eps inspired)."""

from __future__ import annotations

import math
from typing import Optional, Tuple

from environment.scrubber.eps.types import SarjReading


class MockSarj:
    """
    Simplified solar alpha rotary joint model.

    Maps beta angle (and optional eclipse window) to /solar/voltage.
    """

    def __init__(
        self,
        beta_angle_deg: float = 45.0,
        peak_solar_voltage_v: float = 160.0,
        eclipse_voltage_v: float = 60.0,
        eclipse_window: Optional[Tuple[int, int]] = None,
        eclipse_threshold_v: float = 90.0,
    ):
        self.beta_angle_deg = beta_angle_deg
        self.peak_solar_voltage_v = peak_solar_voltage_v
        self.eclipse_voltage_v = eclipse_voltage_v
        self.eclipse_window = eclipse_window
        self.eclipse_threshold_v = eclipse_threshold_v
        self.step_count = 0

    def step(self) -> SarjReading:
        self.step_count += 1
        in_eclipse = self._in_eclipse(self.step_count)
        if in_eclipse:
            solar_v = self.eclipse_voltage_v
        else:
            beta_rad = math.radians(self.beta_angle_deg)
            # 0 deg beta → full sun; 90 deg → minimal generation
            sun_factor = max(0.05, math.cos(beta_rad))
            solar_v = self.peak_solar_voltage_v * sun_factor
        return SarjReading(
            step=self.step_count,
            beta_angle_deg=self.beta_angle_deg,
            solar_voltage_v=round(solar_v, 2),
            in_eclipse=in_eclipse,
        )

    def _in_eclipse(self, step: int) -> bool:
        if self.eclipse_window is None:
            return False
        start, end = self.eclipse_window
        return start <= step <= end

    def is_sunlight_low(self, solar_voltage_v: float) -> bool:
        return solar_voltage_v < self.eclipse_threshold_v
