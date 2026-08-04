"""EPS telemetry types aligned with space_station_eps (BCDUStatus subset)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class BcduMode(str, Enum):
    IDLE = "idle"
    CHARGING = "charging"
    DISCHARGING = "discharging"
    FAULT = "fault"
    SAFE = "safe"


@dataclass
class SarjReading:
    step: int
    beta_angle_deg: float
    solar_voltage_v: float
    in_eclipse: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BcduStatus:
    step: int
    mode: BcduMode
    bus_voltage_v: float
    regulation_voltage_v: float
    current_draw_a: float
    fault: bool
    fault_message: str = ""
    support_w: float = 0.0
    support_steps_remaining: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "mode": self.mode.value,
            "bus_voltage_v": round(self.bus_voltage_v, 2),
            "regulation_voltage_v": round(self.regulation_voltage_v, 2),
            "current_draw_a": round(self.current_draw_a, 2),
            "fault": self.fault,
            "fault_message": self.fault_message,
            "support_w": round(self.support_w, 2),
            "support_steps_remaining": self.support_steps_remaining,
        }


@dataclass
class EpsDiagnostics:
    step: int
    component: str
    level: str  # OK, WARN, ERROR
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "component": self.component,
            "level": self.level,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass
class DischargeResult:
    success: bool
    message: str
    status: Optional[BcduStatus] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "status": self.status.to_dict() if self.status else None,
        }
