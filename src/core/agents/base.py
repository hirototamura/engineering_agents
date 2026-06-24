"""Minimal Agent / Team abstractions for ECLSS scenario agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.agents.types import AgentMessage


@dataclass(frozen=True)
class Persona:
    agent_id: str
    persona: str


@dataclass
class DeliberationContext:
    step: int
    phase: str
    situation: str
    step_discourse: list[AgentMessage]
    team_discourse: list[AgentMessage]
    agent_memory: list[str]


class Team(ABC):
    """Scenario agent team — ``context`` is ``SimulatorProtocol`` or ``EclssBackend``."""

    @abstractmethod
    def run_step(self, context: Any, observation: Any) -> Any: ...

    @abstractmethod
    def apply_outcome(self, context: Any, outcome: Any) -> Any: ...
