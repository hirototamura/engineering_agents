"""Simulator boundary types and protocol contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class HealthStatus(str, Enum):
    SAFE = "safe"
    WARNING = "warning"
    CRITICAL = "critical"


class CommandKind(str, Enum):
    SET_FAN_SPEED = "set_fan_speed"
    ENABLE_BYPASS = "enable_bypass"
    REDUCE_LOAD = "reduce_load"
    REQUEST_EPS_BOOST = "request_eps_boost"


class DesignChangeKind(str, Enum):
    ADD_NODE = "add_node"
    ADD_EDGE = "add_edge"
    SET_PARAMETER = "set_parameter"


@dataclass
class TopologyNode:
    id: str
    name: str
    kind: str  # e.g. scrubber, manifold, cabin


@dataclass
class TopologyEdge:
    source: str
    target: str
    kind: str = "flow"  # flow, bypass, power


@dataclass
class TopologyGraph:
    nodes: List[TopologyNode] = field(default_factory=list)
    edges: List[TopologyEdge] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [asdict(n) for n in self.nodes],
            "edges": [asdict(e) for e in self.edges],
        }


@dataclass
class TelemetrySnapshot:
    step: int
    co2_ppm: float
    scrubber_efficiency: float
    power_margin_w: float
    fan_speed: float
    bypass_enabled: bool
    load_reduced: bool
    eps_support_w: float = 0.0
    eps_support_steps_remaining: int = 0
    anomaly_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HealthMetrics:
    step: int
    co2_status: HealthStatus
    power_status: HealthStatus
    overall: HealthStatus

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "co2_status": self.co2_status.value,
            "power_status": self.power_status.value,
            "overall": self.overall.value,
        }


@dataclass
class RecoveryCommand:
    kind: CommandKind
    value: Any
    issued_by: str = "operator"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "value": self.value,
            "issued_by": self.issued_by,
        }


@dataclass
class DesignChange:
    kind: DesignChangeKind
    payload: Dict[str, Any]
    proposed_by: str = "design_engineer"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "payload": self.payload,
            "proposed_by": self.proposed_by,
        }


@dataclass
class DesignState:
    topology: TopologyGraph
    parameters: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topology": self.topology.to_dict(),
            "parameters": dict(self.parameters),
        }


@dataclass
class CommandResult:
    success: bool
    message: str
    telemetry: Optional[TelemetrySnapshot] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "telemetry": self.telemetry.to_dict() if self.telemetry else None,
        }


@dataclass
class AnomalySpec:
    name: str
    start_step: int
    scrubber_efficiency_decay_per_step: float = 0.01
    power_margin_decay_per_step: float = 5.0
    co2_production_multiplier: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@runtime_checkable
class SimulatorProtocol(Protocol):
    def step(self) -> TelemetrySnapshot: ...

    def apply_command(self, cmd: RecoveryCommand) -> CommandResult: ...

    def apply_design_change(self, change: DesignChange) -> DesignState: ...

    def get_topology(self) -> TopologyGraph: ...

    def get_design_parameters(self) -> Dict[str, float]: ...

    def get_design_state(self) -> DesignState: ...

    def inject_anomaly(self, spec: AnomalySpec) -> None: ...
