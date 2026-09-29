"""Thinking capture: think tags, vLLM reasoning_content, Ollama thinking."""

from __future__ import annotations

from core.llm.base import LLMGeneration, invoke_llm
from core.llm.ollama import OllamaClient
from core.llm.parsing import combine_thinking, extract_thinking_text, parse_json_response
from core.llm.vllm import VllmClient


def test_extract_thinking_text_closed_and_unclosed():
    assert extract_thinking_text("<think>first</think>\n{\"ok\": true}") == "first"
    assert extract_thinking_text("<thinking>keep going") == "keep going"
    assert extract_thinking_text('{"message": "no tags"}') == ""


def test_parse_json_response_keeps_thinking_after_strip():
    raw = '<think>why this tool</think>\n{"message": "next", "reasoning": "data"}'
    parsed = parse_json_response(raw, required=("message",))
    assert parsed.status == "ok"
    assert parsed.data["message"] == "next"
    assert parsed.thinking == "why this tool"


def test_combine_thinking_dedupes_substring():
    assert combine_thinking("short", "short and longer") == "short and longer"
    assert combine_thinking("same", "same") == "same"


def test_invoke_llm_reads_generate_result_thinking():
    class Fake:
        def generate_result(self, prompt: str) -> LLMGeneration:
            return LLMGeneration(text='{"message":"ok"}', thinking="provider thought")

        def generate(self, prompt: str) -> str:
            raise AssertionError("generate() should not be used when generate_result exists")

    result = invoke_llm(Fake(), "ping")
    assert result.text.startswith("{")
    assert result.thinking == "provider thought"


def test_invoke_llm_extracts_think_tags_from_generate_only_clients():
    class Fake:
        def generate(self, prompt: str) -> str:
            return "<think>read telemetry</think>\n{\"message\":\"ok\"}"

    result = invoke_llm(Fake(), "ping")
    assert result.thinking == "read telemetry"


def test_vllm_generate_result_keeps_reasoning_content(monkeypatch):
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"message":"ok"}',
                            "reasoning_content": "long reasoning",
                        }
                    }
                ]
            }

    client = VllmClient(think=True, max_tokens=2048)
    monkeypatch.setattr(client._session, "post", lambda *args, **kwargs: FakeResponse())
    result = client.generate_result("design review")
    assert result.text.startswith("{")
    assert result.thinking == "long reasoning"
    assert client.generate("design review") == result.text


def test_ollama_generate_result_keeps_thinking_field(monkeypatch):
    captured = {}

    class FakeResponse:
        content = b"{}"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "response": '{"message":"ok"}',
                "thinking": "size ARS from dwell, not from the summary",
            }

    def fake_post(url, json, timeout):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("core.llm.ollama.requests.post", fake_post)
    client = OllamaClient(think=True)
    result = client.generate_result("design review")
    assert captured["json"]["think"] is True
    assert result.text.startswith("{")
    assert result.thinking == "size ARS from dwell, not from the summary"
