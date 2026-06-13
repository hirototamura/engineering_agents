"""Datatypes for SSOS ECLSS bridge and smoke tests."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ArsGoal:
    initial_co2_mass: float = 1800.0
    initial_moisture_content: float = 25.0
    initial_contaminants: float = 5.0

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class ActionResult:
    """Generic action outcome (ARS, OGS, WRS)."""

    success: bool
    summary_message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArsActionResult:
    success: bool
    cycles_completed: int = 0
    total_vents: int = 0
    total_co2_vented: float = 0.0
    summary_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_action_result(self) -> ActionResult:
        return ActionResult(
            success=self.success,
            summary_message=self.summary_message,
            details={
                "cycles_completed": self.cycles_completed,
                "total_vents": self.total_vents,
                "total_co2_vented": self.total_co2_vented,
            },
        )


@dataclass
class OgsGoal:
    input_water_mass: float = 15.0
    iodine_concentration: float = 2.0

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class WrsGoal:
    urine_volume: float = 2.0

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class ServiceResult:
    success: bool
    response_value: float = 0.0
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EclssTelemetrySnapshot:
    """Latest ECLSS storage/diagnostic readings from SSOS topics."""

    co2_storage_kg: Optional[float] = None
    o2_storage_kg: Optional[float] = None
    product_water_reserve_l: Optional[float] = None
    ars_failure_enabled: Optional[bool] = None
    ogs_failure_enabled: Optional[bool] = None
    wrs_failure_enabled: Optional[bool] = None
    raw_topics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EclssSmokeReport:
    """Output of Phase 1a ARS headless smoke (scripts/ssos_eclss_ars_smoke.py)."""

    ok: bool
    launch_hint: str
    topics_found: List[str] = field(default_factory=list)
    actions_found: List[str] = field(default_factory=list)
    ars_goal_sent: bool = False
    ars_result: Optional[ArsActionResult] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": self.ok,
            "launch_hint": self.launch_hint,
            "topics_found": self.topics_found,
            "actions_found": self.actions_found,
            "ars_goal_sent": self.ars_goal_sent,
            "errors": self.errors,
        }
        if self.ars_result is not None:
            payload["ars_result"] = self.ars_result.to_dict()
        return payload
