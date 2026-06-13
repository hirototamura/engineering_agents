"""In-memory EclssBackend stub for local dev and contract tests."""

from __future__ import annotations

from typing import Optional

from environment.ssos.eclss_types import (
    ActionResult,
    ArsGoal,
    EclssTelemetrySnapshot,
    OgsGoal,
    ServiceResult,
    WrsGoal,
)


class MockEclssBackend:
    """No-op backend that satisfies EclssBackend without ROS or SSOS."""

    def __init__(self) -> None:
        self._telemetry = EclssTelemetrySnapshot(
            co2_storage_kg=1800.0,
            o2_storage_kg=500.0,
            product_water_reserve_l=100.0,
        )
        self._failure_flags: dict[str, bool] = {
            "ars": False,
            "ogs": False,
            "wrs": False,
        }
        self.last_ars_goal: Optional[ArsGoal] = None
        self.last_ogs_goal: Optional[OgsGoal] = None

    def poll_telemetry(self) -> EclssTelemetrySnapshot:
        return EclssTelemetrySnapshot(
            co2_storage_kg=self._telemetry.co2_storage_kg,
            o2_storage_kg=self._telemetry.o2_storage_kg,
            product_water_reserve_l=self._telemetry.product_water_reserve_l,
            ars_failure_enabled=self._failure_flags["ars"],
            ogs_failure_enabled=self._failure_flags["ogs"],
            wrs_failure_enabled=self._failure_flags["wrs"],
        )

    def send_air_revitalisation_goal(self, goal: ArsGoal) -> ActionResult:
        self.last_ars_goal = goal
        return ActionResult(success=True, summary_message="mock air_revitalisation complete")

    def send_oxygen_generation_goal(self, goal: OgsGoal) -> ActionResult:
        self.last_ogs_goal = goal
        return ActionResult(
            success=True,
            summary_message="mock oxygen_generation complete",
            details={"total_o2_generated": 120.0},
        )

    def send_water_recovery_goal(self, goal: WrsGoal) -> ActionResult:
        raise NotImplementedError("WRS actions are Phase 2")

    def request_o2(self, amount: float) -> ServiceResult:
        return ServiceResult(success=True, response_value=amount, message="mock o2 delivered")

    def request_co2(self, amount: float) -> ServiceResult:
        return ServiceResult(success=True, response_value=amount, message="mock co2 delivered")

    def request_product_water(self, liters: float) -> ServiceResult:
        raise NotImplementedError("WRS product water is Phase 2")

    def submit_grey_water(self, liters: float) -> ServiceResult:
        raise NotImplementedError("grey water service is Phase 2")

    def set_subsystem_failure(self, subsystem: str, enabled: bool) -> None:
        key = subsystem.lower().removesuffix("_failure")
        if key not in self._failure_flags:
            raise ValueError(f"unknown subsystem: {subsystem!r}")
        self._failure_flags[key] = enabled
