"""Team discourse buffer and per-agent private memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from core.agents.types import AgentMessage, StepAgentOutcome


@dataclass
class AgentMemory:
    agent_id: str
    limit: int = 8
    entries: List[str] = field(default_factory=list)

    def append(self, entry: str) -> None:
        text = entry.strip()
        if not text:
            return
        self.entries.append(text)
        if len(self.entries) > self.limit:
            self.entries = self.entries[-self.limit :]

    def recent(self, n: int | None = None) -> List[str]:
        if n is None:
            return list(self.entries)
        return self.entries[-n:]


@dataclass
class DiscourseBuffer:
    window: int = 12
    messages: List[AgentMessage] = field(default_factory=list)

    def extend(self, new_messages: Iterable[AgentMessage]) -> None:
        self.messages.extend(new_messages)
        if len(self.messages) > self.window:
            self.messages = self.messages[-self.window :]

    def recent(self) -> List[AgentMessage]:
        return list(self.messages)


@dataclass
class TeamMemoryStore:
    agent_ids: List[str]
    memory_limit: int = 8
    discourse_window: int = 12
    discourse: DiscourseBuffer = field(init=False)
    agent_memories: Dict[str, AgentMemory] = field(init=False)

    def __post_init__(self) -> None:
        self.discourse = DiscourseBuffer(window=self.discourse_window)
        self.agent_memories = {
            agent_id: AgentMemory(agent_id=agent_id, limit=self.memory_limit)
            for agent_id in self.agent_ids
        }

    def commit_step(self, outcome: StepAgentOutcome) -> None:
        self.discourse.extend(outcome.messages)
        for msg in outcome.messages:
            memory = self.agent_memories.get(msg.from_role)
            if memory is None:
                continue
            llm_memory = msg.metadata.get("llm_memory")
            if llm_memory:
                memory.append(str(llm_memory))
            summary = f"step {msg.step} [{msg.metadata.get('deliberation_phase', '?')}]: {msg.message}"
            if msg.reasoning:
                summary += f" ({msg.reasoning})"
            memory.append(summary)
        for cmd in outcome.commands:
            issuer = cmd.issued_by or "operator"
            memory = self.agent_memories.get(issuer)
            if memory is not None:
                memory.append(f"step action: {cmd.kind.value} value={cmd.value}")
        for change in outcome.design_changes:
            proposer = change.proposed_by or "design_engineer"
            memory = self.agent_memories.get(proposer)
            if memory is not None:
                memory.append(f"step design: {change.kind.value} {change.payload}")
