"""EclssBackend protocol — thin interface for SSOS ECLSS Action/Service/Topic ops."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from environment.ssos.eclss.types import (
    ActionResult,
    ArsGoal,
    EclssTelemetrySnapshot,
    OgsGoal,
    ServiceResult,
    WrsGoal,
)


@runtime_checkable
class EclssBackend(Protocol):
    """Backend for SSOS ECLSS closed-loop ops (Crew Simulation replacement).

    Phase 1b implements ARS + OGS; Phase 2 adds WRS.
    """

    def poll_telemetry(self) -> EclssTelemetrySnapshot: ...

    def send_air_revitalisation_goal(self, goal: ArsGoal) -> ActionResult: ...

    def send_oxygen_generation_goal(self, goal: OgsGoal) -> ActionResult: ...

    def send_water_recovery_goal(self, goal: WrsGoal) -> ActionResult: ...

    def request_o2(self, amount: float) -> ServiceResult: ...

    def request_co2(self, amount: float) -> ServiceResult: ...

    def request_product_water(self, liters: float) -> ServiceResult: ...

    def submit_grey_water(self, liters: float) -> ServiceResult: ...

    def set_subsystem_failure(self, subsystem: str, enabled: bool) -> None: ...
