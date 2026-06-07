"""Scenario ABC — one runnable experiment (config + sim + optional team)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional

from core.agents.base import Team
from environment.protocol import SimulatorProtocol


class Scenario(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def load_config(self, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: ...

    @abstractmethod
    def build_simulator(self, config: Dict[str, Any]) -> SimulatorProtocol: ...

    @abstractmethod
    def build_team(self, config: Dict[str, Any]) -> Optional[Team]: ...

    @abstractmethod
    def run(
        self,
        output_dir: Optional[Path] = None,
        overrides: Optional[Dict[str, Any]] = None,
        recreate_output: bool = True,
    ) -> Path: ...
