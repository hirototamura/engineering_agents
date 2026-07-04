"""Types for ssos_eclss_loop agent loop (EclssBackend, not SimulatorProtocol)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.agents.types import AgentMessage
from environment.ssos.eclss.types import EclssTelemetrySnapshot


@dataclass
class EclssOperationalCommand:
    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)
    issued_by: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "payload": self.payload,
            "issued_by": self.issued_by,
        }


@dataclass
class EclssLoopObservation:
    step: int
    telemetry: EclssTelemetrySnapshot
    health: Dict[str, Any]


@dataclass
class StepEclssOutcome:
    messages: List[AgentMessage] = field(default_factory=list)
    commands: List[EclssOperationalCommand] = field(default_factory=list)
