import asyncio
import concurrent.futures
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from core.llm.parsing import combine_thinking, extract_thinking_text

# Sized for a 100-agent simultaneous round against lab vLLM (I/O-bound HTTP).
LLM_THREAD_POOL_WORKERS = 128
_thread_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=LLM_THREAD_POOL_WORKERS,
    thread_name_prefix="ea-llm",
)


@dataclass(frozen=True)
class LLMGeneration:
    """Assistant text plus any provider/think-tag reasoning.

    ``generate()`` still returns ``text`` only. Designers that need the
    chain-of-thought call ``generate_result()`` / ``invoke_llm()``.
    """

    text: str
    thinking: str = ""


def invoke_llm(client: Any, prompt: str) -> LLMGeneration:
    """Call an LLM client without dropping think/reasoning content.

    Duck-typed fakes that only implement ``generate()`` still work.
    Provider thinking (vLLM ``reasoning_content``, Ollama ``thinking``)
    is merged with any ``<think>`` bodies in the answer text.
    """
    if client is None:
        return LLMGeneration(text="")
    generate_result = getattr(client, "generate_result", None)
    if callable(generate_result):
        result = generate_result(prompt)
        if isinstance(result, LLMGeneration):
            text = result.text or ""
            return LLMGeneration(
                text=text,
                thinking=combine_thinking(result.thinking, extract_thinking_text(text)),
            )
        if isinstance(result, str):
            return LLMGeneration(text=result, thinking=extract_thinking_text(result))
    generate = getattr(client, "generate", None)
    text = str(generate(prompt) or "") if callable(generate) else ""
    return LLMGeneration(text=text, thinking=extract_thinking_text(text))


class LLMClient(ABC):
    def __init__(self, max_concurrency: int = 0):
        self._max_concurrency = max(0, int(max_concurrency))
        # threading.Semaphore is loop-agnostic. asyncio.Semaphore created in
        # __init__ (or bound on first asyncio.run) breaks on the next step's
        # asyncio.run — "bound to a different event loop".
        self._semaphore: Optional[threading.BoundedSemaphore] = (
            threading.BoundedSemaphore(self._max_concurrency) if self._max_concurrency > 0 else None
        )

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate text from prompt. Returns empty string on error."""
        ...

    @abstractmethod
    def check_connection(self) -> bool:
        """Check if LLM backend is reachable."""
        ...

    def generate_result(self, prompt: str) -> LLMGeneration:
        """Generate text plus any captured thinking. Default wraps ``generate()``."""
        return LLMGeneration(text=self.generate(prompt) or "")

    def _generate_limited(self, prompt: str) -> str:
        return self._generate_result_limited(prompt).text

    def _generate_result_limited(self, prompt: str) -> LLMGeneration:
        if self._semaphore is None:
            return self.generate_result(prompt)
        with self._semaphore:
            return self.generate_result(prompt)

    async def generate_result_async(self, prompt: str) -> LLMGeneration:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_thread_pool, self._generate_result_limited, prompt)

    async def generate_async(self, prompt: str) -> str:
        return (await self.generate_result_async(prompt)).text
