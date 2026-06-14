"""Deterministic health assessment for SSOS ECLSS storage telemetry."""

from __future__ import annotations

from typing import Any, Dict, Optional

from environment.protocol import HealthStatus
from environment.ssos.eclss_types import EclssTelemetrySnapshot


def compute_eclss_storage_health(
    step: int,
    snap: EclssTelemetrySnapshot,
    thresholds: Dict[str, Any],
) -> Dict[str, Any]:
    co2_high = float(thresholds.get("co2_storage_high_kg", 1500.0))
    co2_critical = float(thresholds.get("co2_storage_critical_kg", 2200.0))
    o2_low = float(thresholds.get("o2_storage_low_kg", 450.0))
    water_low = float(thresholds.get("product_water_low_l", 50.0))

    co2_status = _co2_status(snap.co2_storage_kg, co2_high, co2_critical)
    o2_status = _o2_status(snap.o2_storage_kg, o2_low)
    water_status = _water_status(snap.product_water_reserve_l, water_low)
    overall = _worst_status(co2_status, o2_status, water_status)

    return {
        "step": step,
        "co2_status": co2_status.value,
        "o2_status": o2_status.value,
        "water_status": water_status.value,
        "overall": overall.value,
    }


def _co2_status(value: Optional[float], high: float, critical: float) -> HealthStatus:
    if value is None:
        return HealthStatus.WARNING
    if value >= critical:
        return HealthStatus.CRITICAL
    if value >= high:
        return HealthStatus.WARNING
    return HealthStatus.SAFE


def _o2_status(value: Optional[float], low: float) -> HealthStatus:
    if value is None:
        return HealthStatus.WARNING
    if value <= low * 0.75:
        return HealthStatus.CRITICAL
    if value <= low:
        return HealthStatus.WARNING
    return HealthStatus.SAFE


def _water_status(value: Optional[float], low: float) -> HealthStatus:
    if value is None:
        return HealthStatus.SAFE
    if value <= low * 0.5:
        return HealthStatus.CRITICAL
    if value <= low:
        return HealthStatus.WARNING
    return HealthStatus.SAFE


def _worst_status(*statuses: HealthStatus) -> HealthStatus:
    order = {HealthStatus.SAFE: 0, HealthStatus.WARNING: 1, HealthStatus.CRITICAL: 2}
    return max(statuses, key=lambda s: order[s])
