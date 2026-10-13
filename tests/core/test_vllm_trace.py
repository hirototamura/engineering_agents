"""Opt-in vLLM audits preserve the actual request without secret reasoning."""

from __future__ import annotations

import hashlib
import json

import requests

from core.llm.vllm import VllmClient


class _Response:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "id": "chatcmpl-test",
            "model": "served-qwen-27b",
            "usage": {"prompt_tokens": 9, "completion_tokens": 17, "total_tokens": 26},
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "content": '<think>private in-text reasoning</think>\n{"candidate": 3}',
                    "reasoning_content": "private provider reasoning",
                },
            }],
        }


def _load_trace(root):
    files = list(root.glob("*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text()), files[0]


def test_trace_is_opt_in(monkeypatch, tmp_path):
    monkeypatch.delenv("EA_LLM_TRACE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    client = VllmClient()
    monkeypatch.setattr(client._session, "post", lambda *args, **kwargs: _Response())
    assert client.generate_result("example").text.endswith('{"candidate": 3}')
    assert list(tmp_path.iterdir()) == []


def test_trace_records_actual_fitted_request_without_auth_or_reasoning(monkeypatch, tmp_path):
    monkeypatch.setenv("EA_LLM_TRACE_DIR", str(tmp_path / "audit"))
    monkeypatch.setenv("VLLM_MAX_MODEL_LEN", "1024")
    client = VllmClient(
        base_url="http://trace-user:trace-password@server:8001/v1",
        model="qwen-27b", temperature=0.1, max_tokens=256,
        think=True, api_key="secret-api-key",
    )
    # A query/fragment is deliberately injected to verify that URL tokens do
    # not become part of the persisted endpoint.
    client.api_url += "?token=query-secret#private-fragment"
    sent = {}

    def fake_post(url, json, headers, timeout):
        sent.update(json)
        assert headers["Authorization"] == "Bearer secret-api-key"
        return _Response()

    monkeypatch.setattr(client._session, "post", fake_post)
    result = client.generate_result("HEAD" + "x" * 10_000 + "末尾")
    assert result.thinking  # Existing client callers still receive reasoning.
    trace, trace_path = _load_trace(tmp_path / "audit")
    prompt = sent["messages"][0]["content"]
    request = trace["request"]
    assert prompt != "HEAD" + "x" * 10_000 + "末尾"
    assert (trace_path.parent / request["prompt_file"]).read_text() == prompt
    assert request["prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
    assert request["prompt_char_count"] == len(prompt)
    assert request["prompt_byte_count"] == len(prompt.encode())
    assert request["url"] == "http://server:8001/v1/chat/completions"
    assert request["model"] == "qwen-27b"
    assert request["temperature"] == 0.1
    assert request["max_tokens"] == sent["max_tokens"]
    assert request["think"] is True
    assert request["thinking_token_budget"] == sent["thinking_token_budget"]
    assert trace["status"] == "succeeded"
    assert trace["http_status"] == 200
    assert trace["wall_seconds"] >= 0
    assert trace["response"]["model"] == "served-qwen-27b"
    assert trace["response"]["usage"]["total_tokens"] == 26
    assert trace["response"]["finish_reason"] == "stop"
    assert trace["response"]["assistant_final"] == {"candidate": 3}
    assert trace["response"]["reasoning_char_count"] == len(result.thinking)
    persisted = trace_path.read_text()
    for secret in ("secret-api-key", "trace-user", "trace-password", "query-secret",
                   "private-fragment", "private in-text reasoning", "private provider reasoning"):
        assert secret not in persisted
    assert list(trace_path.parent.glob("*.tmp")) == []


def test_trace_keeps_clamped_tokens_and_unique_request_files(monkeypatch, tmp_path):
    monkeypatch.setenv("EA_LLM_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("VLLM_MAX_MODEL_LEN", "1024")
    client = VllmClient(max_tokens=4096, think=False)
    monkeypatch.setattr(client._session, "post", lambda *args, **kwargs: _Response())
    for _ in range(2):
        client.generate_result("example")
    traces = [json.loads(path.read_text()) for path in tmp_path.glob("*.json")]
    assert len(traces) == 2
    assert len({trace["request_id"] for trace in traces}) == 2
    for trace in traces:
        assert trace["request"]["requested_max_tokens"] == 4096
        assert trace["request"]["max_tokens"] == 767
        assert trace["request"]["thinking_token_budget"] is None
        assert (tmp_path / trace["request"]["prompt_file"]).is_file()


def test_http_failure_trace_excludes_response_body_and_error_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("EA_LLM_TRACE_DIR", str(tmp_path))

    class ErrorResponse(_Response):
        status_code = 503
        text = "private response body secret-api-key"

        def raise_for_status(self):
            raise requests.HTTPError("secret-api-key in error", response=self)

    client = VllmClient(api_key="secret-api-key")
    monkeypatch.setattr(client._session, "post", lambda *args, **kwargs: ErrorResponse())
    assert client.generate_result("example").error
    trace, path = _load_trace(tmp_path)
    assert trace["status"] == "failed"
    assert trace["http_status"] == 503
    assert trace["error_type"] == "HTTPError"
    assert "secret-api-key" not in path.read_text()
    assert "private response body" not in path.read_text()


def test_transport_failure_trace_and_trace_write_failure_do_not_change_results(monkeypatch, tmp_path):
    monkeypatch.setenv("EA_LLM_TRACE_DIR", str(tmp_path / "audit"))
    client = VllmClient()

    def fail_post(*args, **kwargs):
        raise requests.ConnectionError("server unavailable")

    monkeypatch.setattr(client._session, "post", fail_post)
    assert client.generate_result("example").error == "server unavailable"
    trace, _ = _load_trace(tmp_path / "audit")
    assert trace["status"] == "failed"
    assert trace["http_status"] is None
    assert trace["error_type"] == "ConnectionError"

    invalid_directory = tmp_path / "ordinary-file"
    invalid_directory.write_text("not a directory")
    monkeypatch.setenv("EA_LLM_TRACE_DIR", str(invalid_directory))
    monkeypatch.setattr(client._session, "post", lambda *args, **kwargs: _Response())
    assert client.generate_result("example").text.endswith('{"candidate": 3}')


def test_trace_does_not_store_truncated_thinking_as_a_final_answer(monkeypatch, tmp_path):
    monkeypatch.setenv("EA_LLM_TRACE_DIR", str(tmp_path))

    class TruncatedResponse(_Response):
        def json(self):
            return {"choices": [{"finish_reason": "length", "message": {
                "content": "<think>unfinished private reasoning",
            }}]}

    client = VllmClient(think=True)
    monkeypatch.setattr(client._session, "post", lambda *args, **kwargs: TruncatedResponse())
    client.generate_result("example")
    trace, path = _load_trace(tmp_path)
    assert trace["response"]["assistant_final"] == ""
    assert trace["response"]["finish_reason"] == "length"
    assert trace["response"]["reasoning_char_count"] > 0
    assert "unfinished private reasoning" not in path.read_text()
