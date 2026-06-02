from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.llm.base import LLMClient


class Agent(ABC):
    def __init__(
        self,
        agent_id: int,
        initial_position: tuple,
        llm_client: LLMClient,
        communication_radius: float,
        memory_limit: int = 20,
        memory_size: int = 5,
        message_history_limit: int = 10,
        message_context_size: int = 3,
    ):
        self.id = agent_id
        self.position = initial_position
        self.llm_client = llm_client
        self.communication_radius = communication_radius
        self.memory_limit = memory_limit
        self.memory_size = memory_size
        self.message_history_limit = message_history_limit
        self.message_context_size = message_context_size
        self.memory: List[str] = []
        self.received_messages: List[Dict] = []
        self.step_received_messages: List[Dict] = []

    @abstractmethod
    def build_message_prompt(self, nearby_agents: List["Agent"], env_state: Any) -> str: ...

    @abstractmethod
    def build_action_prompt(self, nearby_agents: List["Agent"], env_state: Any) -> str: ...

    @abstractmethod
    def _parse_message_response(self, response: str) -> Dict: ...

    @abstractmethod
    def _parse_action_response(self, response: str) -> Dict: ...

    def build_combined_prompt(self, nearby_agents: List["Agent"], env_state: Any) -> Optional[str]:
        return None

    def _parse_combined_response(self, response: str) -> Dict:
        msg = self._parse_message_response(response)
        act = self._parse_action_response(response)
        return {**act, "message": msg.get("message", "")}

    def decide_combined(self, nearby_agents: List["Agent"], env_state: Any) -> Dict:
        prompt = self.build_combined_prompt(nearby_agents, env_state)
        if prompt is None:
            msg = self.decide_message(nearby_agents, env_state)
            act = self.decide_action(nearby_agents, env_state)
            return {**act, "message": msg.get("message", "")}
        response = self.llm_client.generate(prompt)
        return self._parse_combined_response(response)

    async def decide_combined_async(self, nearby_agents: List["Agent"], env_state: Any) -> Dict:
        prompt = self.build_combined_prompt(nearby_agents, env_state)
        if prompt is None:
            return self.decide_combined(nearby_agents, env_state)
        response = await self.llm_client.generate_async(prompt)
        return self._parse_combined_response(response)

    async def decide_message_async(self, nearby_agents: List["Agent"], env_state: Any) -> Dict:
        prompt = self.build_message_prompt(nearby_agents, env_state)
        response = await self.llm_client.generate_async(prompt)
        return self._parse_message_response(response)

    async def decide_action_async(self, nearby_agents: List["Agent"], env_state: Any) -> Dict:
        prompt = self.build_action_prompt(nearby_agents, env_state)
        response = await self.llm_client.generate_async(prompt)
        return self._parse_action_response(response)

    def decide_message(self, nearby_agents: List["Agent"], env_state: Any) -> Dict:
        prompt = self.build_message_prompt(nearby_agents, env_state)
        response = self.llm_client.generate(prompt)
        return self._parse_message_response(response)

    def decide_action(self, nearby_agents: List["Agent"], env_state: Any) -> Dict:
        prompt = self.build_action_prompt(nearby_agents, env_state)
        response = self.llm_client.generate(prompt)
        return self._parse_action_response(response)

    def add_memory(self, memory: str):
        self.memory.append(memory)
        if len(self.memory) > self.memory_limit:
            self.memory.pop(0)

    def receive_message(self, sender_id: int, message: str, **metadata):
        entry = {"sender": sender_id, "message": message}
        for key, value in metadata.items():
            if value is not None:
                entry[key] = value
        self.received_messages.append(entry)
        if len(self.received_messages) > self.message_history_limit:
            self.received_messages.pop(0)
        self.step_received_messages.append(entry)
