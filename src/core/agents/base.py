"""Minimal Agent / Team abstractions for ECLSS scenario agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.agents.types import AgentMessage, AgentObservation, StepAgentOutcome
    from environment.protocol import SimulatorProtocol


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
    @abstractmethod
    def run_step(self, sim: SimulatorProtocol, obs: AgentObservation) -> StepAgentOutcome: ...

    @abstractmethod
    def apply_outcome(self, sim: SimulatorProtocol, outcome: StepAgentOutcome) -> None: ...
