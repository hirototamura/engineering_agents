"""Simulator boundary layer (SSOS / ECLSS mock and adapters)."""

from environment.protocol import (
    AnomalySpec,
    CommandResult,
    DesignState,
    RecoveryCommand,
    SimulatorProtocol,
    TelemetrySnapshot,
)
from environment.ssos.mock_eclss import MockEclssSimulator

__all__ = [
    "AnomalySpec",
    "CommandResult",
    "DesignState",
    "MockEclssSimulator",
    "RecoveryCommand",
    "SimulatorProtocol",
    "TelemetrySnapshot",
]
