"""Smoke tests that core packages import correctly."""

from core.agents import AgentMessage, Persona, Team
from core.agents.memory import AgentMemory, DiscourseBuffer, TeamMemoryStore
from core.agents.persona import PersonaAgent, PersonaPromptBuilder
from core.event_log import EventLog
from core.llm.base import LLMClient
from core.llm.ollama import OllamaClient
from core.llm.parsing import parse_json_response
from core.scenario import Scenario


def test_core_imports():
    assert Team is not None
    assert Scenario is not None
    assert Persona is not None
    assert PersonaAgent is not None
    assert EventLog is not None
    assert LLMClient is not None
    assert OllamaClient is not None


def test_parse_json_response_ok():
    parsed = parse_json_response('{"action": "stay", "reasoning": "ok"}', required=["action"])
    assert parsed.status == "ok"
    assert parsed.data["action"] == "stay"
