"""Smoke tests that core packages import correctly."""

from core.agent import Agent
from core.event_log import EventLog
from core.llm.base import LLMClient
from core.llm.ollama import OllamaClient
from core.llm.parsing import parse_json_response
from core.simulation import Simulation


def test_core_imports():
    assert Agent is not None
    assert Simulation is not None
    assert EventLog is not None
    assert LLMClient is not None
    assert OllamaClient is not None


def test_parse_json_response_ok():
    parsed = parse_json_response('{"action": "stay", "reasoning": "ok"}', required=["action"])
    assert parsed.status == "ok"
    assert parsed.data["action"] == "stay"
