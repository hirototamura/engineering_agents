"""Parse ROS 2 CLI echo output into EPS dataclasses."""

from __future__ import annotations

import re
from typing import Optional

from environment.scrubber.eps.types import BcduMode, BcduStatus, SarjReading


def _extract_float(text: str, pattern: str) -> Optional[float]:
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_bool(text: str, pattern: str) -> Optional[bool]:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    token = match.group(1).strip().lower()
    if token in {"true", "1"}:
        return True
    if token in {"false", "0"}:
        return False
    return None


def _extract_string(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def parse_bcdu_mode(text: str) -> BcduMode:
    for pattern in (
        r"mode:\s*'?([a-z]+)'?",
        r"mode='([a-z]+)'",
        r'mode="([a-z]+)"',
    ):
        value = _extract_string(text, pattern)
        if value:
            try:
                return BcduMode(value.lower())
            except ValueError:
                return BcduMode.IDLE
    return BcduMode.IDLE


def parse_bcdu_status(
    text: str,
    *,
    step: int = 0,
    support_w: float = 0.0,
    support_steps_remaining: int = 0,
) -> Optional[BcduStatus]:
    """Parse ``ros2 topic echo`` output for ``BCDUStatus`` (YAML or Jazzy repr)."""
    if not text.strip():
        return None

    bus_voltage = _extract_float(text, r"bus_voltage:\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)")
    if bus_voltage is None:
        bus_voltage = _extract_float(text, r"bus_voltage=([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)")

    regulation_voltage = _extract_float(
        text, r"regulation_voltage:\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)"
    )
    if regulation_voltage is None:
        regulation_voltage = _extract_float(
            text, r"regulation_voltage=([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)"
        )

    current_draw = _extract_float(text, r"current_draw:\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)")
    if current_draw is None:
        current_draw = _extract_float(
            text, r"current_draw=([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)"
        )

    fault = _extract_bool(text, r"fault:\s*(true|false)")
    if fault is None:
        fault = _extract_bool(text, r"fault=(true|false)")

    fault_message = _extract_string(text, r"fault_message:\s*'([^']*)'")
    if fault_message is None:
        fault_message = _extract_string(text, r'fault_message:\s*"([^"]*)"')
    if fault_message is None:
        fault_message = _extract_string(text, r"fault_message='([^']*)'")

    if bus_voltage is None and regulation_voltage is None and current_draw is None:
        return None

    return BcduStatus(
        step=step,
        mode=parse_bcdu_mode(text),
        bus_voltage_v=bus_voltage or 0.0,
        regulation_voltage_v=regulation_voltage or 0.0,
        current_draw_a=current_draw or 0.0,
        fault=fault or False,
        fault_message=fault_message or "",
        support_w=support_w,
        support_steps_remaining=support_steps_remaining,
    )


def estimate_discharge_w(status: BcduStatus) -> float:
    """Phase 3a: watts from SSOS BCDU when discharging."""
    if status.mode != BcduMode.DISCHARGING:
        return 0.0
    draw = abs(status.current_draw_a)
    if draw <= 0.0:
        return 0.0
    bus = max(status.bus_voltage_v, 1.0)
    return round(draw * bus, 2)


def sarj_reading_from_topics(
    *,
    step: int,
    solar_voltage_v: float,
    beta_angle_deg: float,
    eclipse_threshold_v: float = 90.0,
) -> SarjReading:
    in_eclipse = solar_voltage_v < eclipse_threshold_v
    return SarjReading(
        step=step,
        beta_angle_deg=beta_angle_deg,
        solar_voltage_v=round(solar_voltage_v, 2),
        in_eclipse=in_eclipse,
    )
