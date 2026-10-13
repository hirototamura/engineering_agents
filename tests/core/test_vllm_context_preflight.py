"""Engineering prompts remain complete and use the served model's tokenizer."""
from unittest.mock import Mock

from core.llm.vllm import VllmClient


def reply(body):
    response = Mock()
    response.json.return_value = body
    return response


def test_server_tokenizer_preserves_a_prompt_that_the_character_heuristic_would_cut(monkeypatch):
    monkeypatch.setenv("VLLM_TOKENIZE_PREFLIGHT", "true")
    client = VllmClient(base_url="http://example.test:8001/v1", max_tokens=4096, think=True)
    session = Mock()
    session.post.side_effect = [reply({"count": 24000, "max_model_len": 32768}),
        reply({"choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]})]
    client._local.session = session
    prompt = "structured requirement data " * 4000
    generation = client.generate_result(prompt)
    assert not generation.error
    assert session.post.call_args_list[0].args[0] == "http://example.test:8001/tokenize"
    assert session.post.call_args_list[0].kwargs["json"]["chat_template_kwargs"] == {"enable_thinking": True}
    assert session.post.call_args_list[1].kwargs["json"]["messages"][0]["content"] == prompt


def test_over_budget_structured_prompt_is_rejected_without_inference(monkeypatch):
    monkeypatch.setenv("VLLM_TOKENIZE_PREFLIGHT", "true")
    client = VllmClient(max_tokens=4096)
    session = Mock()
    session.post.return_value = reply({"count": 30000, "max_model_len": 32768})
    client._local.session = session
    generation = client.generate_result("data")
    assert "no inference or truncation performed" in generation.error
    assert session.post.call_count == 1
