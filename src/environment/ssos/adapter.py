"""Real SSOS adapter stub — swap in when ROS2 runtime is available."""

from __future__ import annotations

from typing import Dict, List, Optional

from environment.protocol import (
    AnomalySpec,
    CommandResult,
    DesignState,
    RecoveryCommand,
    TelemetrySnapshot,
    TopologyGraph,
)
from environment.ssos.mock_eclss import MockEclssSimulator
from environment.ssos.ros2_eps_bridge import Ros2EpsBridge
from environment.ssos.station_simulator import StationSimulator


class SsosAdapter:
    """Placeholder for real Space Station OS / ROS2 integration.

    Phase 3: use ``StationSimulator`` with ``Ros2EpsBridge`` instead of this stub.
    """

    def __init__(self, repo_path: str | None = None):
        self.repo_path = repo_path
        raise NotImplementedError(
            "Use StationSimulator(MockEclssSimulator(), Ros2EpsBridge()) for Phase 3 EPS. "
            "See environment.ssos.ros2_eps_bridge."
        )

    def step(self) -> TelemetrySnapshot:
        raise NotImplementedError

    def apply_command(self, cmd: RecoveryCommand) -> CommandResult:
        raise NotImplementedError

    def get_topology(self) -> TopologyGraph:
        raise NotImplementedError

    def get_design_parameters(self) -> Dict[str, float]:
        raise NotImplementedError

    def get_design_state(self) -> DesignState:
        raise NotImplementedError

    def inject_anomaly(self, spec: AnomalySpec) -> None:
        raise NotImplementedError


def build_ssos_eps_station(
    eclss: Optional[MockEclssSimulator] = None,
    *,
    topic_timeout_s: float = 10.0,
) -> StationSimulator:
    """ECLSS mock + live SSOS EPS via ROS 2 (Phase 3)."""
    return StationSimulator(
        eclss=eclss or MockEclssSimulator(),
        eps=Ros2EpsBridge(topic_timeout_s=topic_timeout_s),
    )
