import logging
import os
from typing import Any, Dict, Optional

import requests

from core.llm.base import LLMClient, LLMGeneration
from core.llm.parsing import combine_thinking, extract_thinking_text

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:11434"
OLLAMA_BASE_URL_ENV = "OLLAMA_BASE_URL"
API_TIMEOUT = 300
CONNECTION_CHECK_TIMEOUT = 5

_MODEL_CONCURRENCY_DEFAULTS = [
    (["70b", "72b"], 2),
    (["14b", "13b"], 4),
    (["7b", "8b"], 6),
]
_CONCURRENCY_FALLBACK = 8


def _default_concurrency(model: str) -> int:
    lower = model.lower()
    for keywords, limit in _MODEL_CONCURRENCY_DEFAULTS:
        if any(k in lower for k in keywords):
            return limit
    return _CONCURRENCY_FALLBACK


def resolve_ollama_base_url(llm_cfg: Optional[Dict[str, Any]] = None) -> str:
    """Resolve Ollama URL: env OLLAMA_BASE_URL overrides agents.yaml llm.base_url."""
    env_url = os.environ.get(OLLAMA_BASE_URL_ENV, "").strip()
    if env_url:
        return env_url.rstrip("/")
    cfg_url = str((llm_cfg or {}).get("base_url", DEFAULT_BASE_URL)).strip()
    return cfg_url.rstrip("/") or DEFAULT_BASE_URL


def _extract_ollama_thinking(payload: Dict[str, Any]) -> str:
    """Return Ollama ``thinking`` / ``reasoning`` from a generate response."""
    for key in ("thinking", "reasoning"):
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            text = "\n".join(str(item).strip() for item in value if str(item).strip())
        else:
            text = str(value).strip()
        if text:
            return text
    message = payload.get("message")
    if isinstance(message, dict):
        nested = message.get("thinking") or message.get("reasoning")
        if nested:
            return str(nested).strip()
    return ""


class OllamaClient(LLMClient):
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = "llama3.2",
        temperature: float = 0.7,
        max_tokens: int = 200,
        repeat_penalty: float = 1.1,
        repeat_last_n: int = 128,
        min_p: float = 0.05,
        max_concurrency: int = -1,
        json_format: bool = True,
        think: Optional[bool] = None,
        api_timeout: Optional[int] = None,
    ):
        resolved = _default_concurrency(model) if max_concurrency == -1 else max_concurrency
        super().__init__(max_concurrency=resolved)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.repeat_penalty = repeat_penalty
        self.repeat_last_n = repeat_last_n
        self.min_p = min_p
        self.json_format = json_format
        self.think = think
        self.api_timeout = api_timeout or API_TIMEOUT
        self.api_url = f"{self.base_url}/api/generate"

    def generate(self, prompt: str) -> str:
        return self.generate_result(prompt).text

    def generate_result(self, prompt: str) -> LLMGeneration:
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                    "repeat_penalty": self.repeat_penalty,
                    "repeat_last_n": self.repeat_last_n,
                    "min_p": self.min_p,
                },
            }
            if self.json_format:
                payload["format"] = "json"
            if self.think is not None:
                payload["think"] = self.think
            response = requests.post(self.api_url, json=payload, timeout=self.api_timeout)
            response.raise_for_status()
            body = response.json() if response.content else {}
            if not isinstance(body, dict):
                body = {}
            text = str(body.get("response", "") or "").strip()
            thinking = combine_thinking(
                _extract_ollama_thinking(body),
                extract_thinking_text(text),
            )
            return LLMGeneration(text=text, thinking=thinking)
        except Exception as e:
            logger.error("OllamaClient.generate error: %s", e)
            return LLMGeneration(text="")

    def check_connection(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=CONNECTION_CHECK_TIMEOUT)
            return response.status_code == 200
        except Exception:
            return False
