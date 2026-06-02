"""Real SSOS adapter stub — swap in when ROS2 runtime is available."""

from __future__ import annotations

from typing import Dict, List

from environment.protocol import (
    AnomalySpec,
    CommandResult,
    DesignChange,
    DesignState,
    RecoveryCommand,
    TelemetrySnapshot,
    TopologyGraph,
)


class SsosAdapter:
    """Placeholder for real Space Station OS / ROS2 integration."""

    def __init__(self, repo_path: str | None = None):
        self.repo_path = repo_path
        raise NotImplementedError(
            "Real SSOS adapter is not implemented in Week-1 MVP. "
            "Use environment.ssos.mock_eclss.MockEclssSimulator instead."
        )

    def step(self) -> TelemetrySnapshot:
        raise NotImplementedError

    def apply_command(self, cmd: RecoveryCommand) -> CommandResult:
        raise NotImplementedError

    def apply_design_change(self, change: DesignChange) -> DesignState:
        raise NotImplementedError

    def get_topology(self) -> TopologyGraph:
        raise NotImplementedError

    def get_design_parameters(self) -> Dict[str, float]:
        raise NotImplementedError

    def get_design_state(self) -> DesignState:
        raise NotImplementedError

    def inject_anomaly(self, spec: AnomalySpec) -> None:
        raise NotImplementedError
