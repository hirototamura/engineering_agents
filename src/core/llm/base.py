import asyncio
import concurrent.futures
from abc import ABC, abstractmethod
from typing import Optional

_thread_pool = concurrent.futures.ThreadPoolExecutor()


class LLMClient(ABC):
    def __init__(self, max_concurrency: int = 0):
        self._max_concurrency = max_concurrency
        self._semaphore: Optional[asyncio.Semaphore] = None

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate text from prompt. Returns empty string on error."""
        ...

    @abstractmethod
    def check_connection(self) -> bool:
        """Check if LLM backend is reachable."""
        ...

    async def generate_async(self, prompt: str) -> str:
        loop = asyncio.get_running_loop()
        if self._max_concurrency > 0:
            if self._semaphore is None:
                self._semaphore = asyncio.Semaphore(self._max_concurrency)
            async with self._semaphore:
                return await loop.run_in_executor(_thread_pool, self.generate, prompt)
        return await loop.run_in_executor(_thread_pool, self.generate, prompt)
