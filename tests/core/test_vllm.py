"""Unit tests for the OpenAI-compatible vLLM client."""

from __future__ import annotations

from core.llm.vllm import (
    DEFAULT_BASE_URL,
    VllmClient,
    looks_like_ollama_url,
    normalize_vllm_base_url,
    resolve_vllm_base_url,
    resolve_vllm_model,
)


def test_normalize_vllm_base_url_appends_v1():
    assert normalize_vllm_base_url("http://10.10.0.108:8000") == "http://10.10.0.108:8000/v1"
    assert normalize_vllm_base_url("http://10.10.0.108:8000/v1/") == "http://10.10.0.108:8000/v1"


def test_looks_like_ollama_url():
    assert looks_like_ollama_url("http://localhost:11434")
    assert looks_like_ollama_url("http://host.docker.internal:11434")
    assert not looks_like_ollama_url("http://10.10.0.108:8000/v1")


def test_resolve_vllm_defaults_when_yaml_still_points_at_ollama(monkeypatch):
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    monkeypatch.delenv("VLLM_MODEL", raising=False)
    cfg = {"base_url": "http://localhost:11434", "model": "gemma4:e4b"}
    assert resolve_vllm_base_url(cfg) == DEFAULT_BASE_URL
    assert resolve_vllm_model(cfg) == "qwen3-8b"


def test_resolve_vllm_keeps_explicit_lab_endpoint(monkeypatch):
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    monkeypatch.delenv("VLLM_MODEL", raising=False)
    cfg = {"base_url": "http://10.10.0.108:8001", "model": "qwen3-32b"}
    assert resolve_vllm_base_url(cfg) == "http://10.10.0.108:8001/v1"
    assert resolve_vllm_model(cfg) == "qwen3-32b"


def test_resolve_vllm_env_overrides_yaml(monkeypatch):
    monkeypatch.setenv("VLLM_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("VLLM_MODEL", "qwen3-32b")
    cfg = {"base_url": "http://10.10.0.108:8000/v1", "model": "qwen3-8b"}
    assert resolve_vllm_base_url(cfg) == "http://127.0.0.1:8000/v1"
    assert resolve_vllm_model(cfg) == "qwen3-32b"


def test_vllm_generate_posts_chat_completions(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "  hello  "}}]}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("core.llm.vllm.requests.post", fake_post)
    client = VllmClient(think=False, api_timeout=12)
    assert client.generate("ping") == "hello"
    assert captured["url"] == "http://10.10.0.108:8000/v1/chat/completions"
    assert captured["json"]["model"] == "qwen3-8b"
    assert captured["json"]["messages"] == [{"role": "user", "content": "ping"}]
    assert captured["json"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured["headers"]["Authorization"] == "Bearer dummy"


def test_vllm_check_connection_hits_models(monkeypatch):
    class FakeResponse:
        status_code = 200

    monkeypatch.setattr(
        "core.llm.vllm.requests.get",
        lambda *args, **kwargs: FakeResponse(),
    )
    assert VllmClient().check_connection() is True


def test_vllm_generate_returns_empty_on_error(monkeypatch):
    monkeypatch.setattr(
        "core.llm.vllm.requests.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")),
    )
    assert VllmClient().generate("ping") == ""
