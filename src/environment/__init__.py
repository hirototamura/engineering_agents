"""Simulator boundary layer (SSOS / ECLSS mock and adapters)."""

from environment.protocol import (
    AnomalySpec,
    CommandResult,
    DesignChange,
    DesignState,
    RecoveryCommand,
    SimulatorProtocol,
    TelemetrySnapshot,
)
from environment.ssos.mock_eclss import MockEclssSimulator

__all__ = [
    "AnomalySpec",
    "CommandResult",
    "DesignChange",
    "DesignState",
    "MockEclssSimulator",
    "RecoveryCommand",
    "SimulatorProtocol",
    "TelemetrySnapshot",
]
