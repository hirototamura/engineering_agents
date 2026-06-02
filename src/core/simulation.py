import asyncio
import logging
import math
from typing import Any, Callable, List, Optional

from core.agent import Agent

logger = logging.getLogger(__name__)


class Simulation:
    """Domain-agnostic multi-agent step loop (two-phase message then action)."""

    def __init__(
        self,
        agents: List[Agent],
        duration: int,
        grid=None,
        on_step_start: Optional[Callable[[int, List[Agent]], None]] = None,
        on_step_end: Optional[Callable[[int, List[Agent]], None]] = None,
        use_two_phase: bool = True,
    ):
        self.agents = agents
        self.duration = duration
        self.grid = grid
        self.on_step_start = on_step_start
        self.on_step_end = on_step_end
        self.use_two_phase = use_two_phase
        self.current_step = 0
        self.last_message_decisions = {}
        self.last_action_decisions = {}
        self.last_delivered_messages = []

    @staticmethod
    def _message_decision_fields(decision: dict) -> dict:
        return {
            "message": decision.get("message", ""),
            "message_type": decision.get("message_type"),
            "location": decision.get("location"),
            "value": decision.get("value"),
            "confidence": decision.get("confidence"),
            "requested_action": decision.get("requested_action"),
            "reasoning": decision.get("reasoning", ""),
            "parse_status": decision.get("parse_status"),
            "parse_error": decision.get("parse_error"),
            "raw_response_excerpt": decision.get("raw_response_excerpt", ""),
        }

    def run(self):
        for step in range(self.duration):
            self.current_step = step + 1
            if self.on_step_start:
                self.on_step_start(self.current_step, self.agents)
            if self.use_two_phase:
                self._run_step_two_phase(step)
            else:
                self._run_step(step)
            if self.on_step_end:
                self.on_step_end(self.current_step, self.agents)
        logger.info("Simulation complete after %s steps", self.duration)

    async def run_async(self):
        for step in range(self.duration):
            self.current_step = step + 1
            if self.on_step_start:
                self.on_step_start(self.current_step, self.agents)
            if self.use_two_phase:
                await self._run_step_async_two_phase(step)
            else:
                await self._run_step_async(step)
            if self.on_step_end:
                self.on_step_end(self.current_step, self.agents)
        logger.info("Simulation complete after %s steps", self.duration)

    def _run_step_two_phase(self, step: int):
        env_state = {"step": self.current_step}
        active = [a for a in self.agents if self._is_agent_active(a)]
        inactive = [a for a in self.agents if not self._is_agent_active(a)]

        for agent in self.agents:
            agent.step_received_messages = []

        message_decisions = {}
        nearby_by_id = {}
        for agent in active:
            nearby = self._get_nearby_agents(agent)
            nearby_by_id[agent.id] = nearby
            message_decisions[agent.id] = agent.decide_message(nearby, env_state)

        self._deliver_messages(message_decisions)
        self.last_message_decisions = message_decisions

        action_decisions = {}
        for agent in active:
            action_decisions[agent.id] = agent.decide_action(nearby_by_id[agent.id], env_state)

        for agent in inactive:
            message_decisions[agent.id] = {
                "message": "",
                "reasoning": getattr(agent, "disabled_reason", "inactive"),
            }
            action_decisions[agent.id] = {
                "action": "stay",
                "direction": None,
                "memory": "",
                "reasoning": getattr(agent, "disabled_reason", "inactive"),
                "skipped": True,
            }

        self.last_action_decisions = action_decisions

        for agent in active:
            if message_decisions[agent.id].get("message") and hasattr(agent, "apply_message_cost"):
                agent.apply_message_cost()
        self._apply_actions(action_decisions, env_state)

    def _run_step(self, step: int):
        env_state = {"step": self.current_step}

        message_decisions = {}
        action_decisions = {}
        for agent in self.agents:
            if not self._is_agent_active(agent):
                message_decisions[agent.id] = {
                    "message": "",
                    "reasoning": getattr(agent, "disabled_reason", "inactive"),
                }
                action_decisions[agent.id] = {
                    "action": "stay",
                    "direction": None,
                    "memory": "",
                    "reasoning": getattr(agent, "disabled_reason", "inactive"),
                    "skipped": True,
                }
                continue
            nearby = self._get_nearby_agents(agent)
            combined = agent.decide_combined(nearby, env_state)
            message_decisions[agent.id] = self._message_decision_fields(combined)
            action_decisions[agent.id] = {k: v for k, v in combined.items() if k != "message"}
            if combined.get("message") and hasattr(agent, "apply_message_cost"):
                agent.apply_message_cost()
        self.last_message_decisions = message_decisions

        self._deliver_messages(message_decisions)
        self.last_action_decisions = action_decisions
        self._apply_actions(action_decisions, env_state)

    async def _run_step_async(self, step: int):
        env_state = {"step": self.current_step}
        active = [a for a in self.agents if self._is_agent_active(a)]
        inactive = [a for a in self.agents if not self._is_agent_active(a)]

        async def decide_one(agent):
            nearby = self._get_nearby_agents(agent)
            return agent.id, await agent.decide_combined_async(nearby, env_state)

        results = await asyncio.gather(*[decide_one(a) for a in active])
        combined_by_id = dict(results)

        message_decisions = {}
        action_decisions = {}
        for agent in inactive:
            message_decisions[agent.id] = {
                "message": "",
                "reasoning": getattr(agent, "disabled_reason", "inactive"),
            }
            action_decisions[agent.id] = {
                "action": "stay",
                "direction": None,
                "memory": "",
                "reasoning": getattr(agent, "disabled_reason", "inactive"),
                "skipped": True,
            }
        for agent in active:
            combined = combined_by_id[agent.id]
            message_decisions[agent.id] = self._message_decision_fields(combined)
            action_decisions[agent.id] = {k: v for k, v in combined.items() if k != "message"}
            if combined.get("message") and hasattr(agent, "apply_message_cost"):
                agent.apply_message_cost()
        self.last_message_decisions = message_decisions

        self._deliver_messages(message_decisions)
        self.last_action_decisions = action_decisions
        self._apply_actions(action_decisions, env_state)

    async def _run_step_async_two_phase(self, step: int):
        env_state = {"step": self.current_step}
        active = [a for a in self.agents if self._is_agent_active(a)]
        inactive = [a for a in self.agents if not self._is_agent_active(a)]

        for agent in self.agents:
            agent.step_received_messages = []

        async def decide_msg(agent):
            nearby = self._get_nearby_agents(agent)
            result = await agent.decide_message_async(nearby, env_state)
            return agent.id, nearby, result

        msg_results = await asyncio.gather(*[decide_msg(a) for a in active])
        message_decisions = {aid: r for aid, _, r in msg_results}
        nearby_by_id = {aid: nb for aid, nb, _ in msg_results}

        self._deliver_messages(message_decisions)
        self.last_message_decisions = message_decisions

        async def decide_act(agent):
            nearby = nearby_by_id[agent.id]
            result = await agent.decide_action_async(nearby, env_state)
            return agent.id, result

        act_results = await asyncio.gather(*[decide_act(a) for a in active])
        action_decisions = {aid: r for aid, r in act_results}

        for agent in inactive:
            message_decisions[agent.id] = {
                "message": "",
                "reasoning": getattr(agent, "disabled_reason", "inactive"),
            }
            action_decisions[agent.id] = {
                "action": "stay",
                "direction": None,
                "memory": "",
                "reasoning": getattr(agent, "disabled_reason", "inactive"),
                "skipped": True,
            }

        self.last_action_decisions = action_decisions

        for agent in active:
            msg = message_decisions[agent.id].get("message", "")
            if msg and hasattr(agent, "apply_message_cost"):
                agent.apply_message_cost()
        self._apply_actions(action_decisions, env_state)

    def _deliver_messages(self, message_decisions: dict):
        delivered = []
        for agent in self.agents:
            if not self._is_agent_active(agent):
                continue
            decision = message_decisions[agent.id]
            msg = decision.get("message", "")
            if not msg:
                continue
            to_field = decision.get("to")
            target_set = None
            if isinstance(to_field, int):
                target_set = {to_field}
            elif isinstance(to_field, list):
                target_set = {int(t) for t in to_field if isinstance(t, (int, float))}

            for other in self._get_nearby_agents(agent):
                if other.id == agent.id:
                    continue
                if target_set is not None and other.id not in target_set:
                    continue
                structured = {
                    "message_type": decision.get("message_type"),
                    "location": decision.get("location"),
                    "value": decision.get("value"),
                    "confidence": decision.get("confidence"),
                    "requested_action": decision.get("requested_action"),
                    "addressed": target_set is not None,
                }
                other.receive_message(sender_id=agent.id, message=msg, **structured)
                delivered.append(
                    {
                        "from": agent.id,
                        "to": other.id,
                        "message": msg,
                        **structured,
                        "reasoning": decision.get("reasoning", ""),
                        "parse_status": decision.get("parse_status"),
                        "parse_error": decision.get("parse_error"),
                        "raw_response_excerpt": decision.get("raw_response_excerpt", ""),
                    }
                )
        self.last_delivered_messages = delivered

    def _apply_actions(self, action_decisions: dict, env_state: dict):
        for agent in self.agents:
            if not self._is_agent_active(agent):
                continue
            decision = action_decisions[agent.id]
            memory = decision.get("memory", "")
            if memory:
                agent.add_memory(memory)
            if hasattr(agent, "apply_action"):
                agent.apply_action(decision, self.grid, env_state)

    def _get_nearby_agents(self, agent: Agent) -> List[Agent]:
        if not self._is_agent_active(agent):
            return []
        result = []
        for other in self.agents:
            if other.id == agent.id:
                continue
            if not self._is_agent_active(other):
                continue
            dist = math.sqrt(
                (agent.position[0] - other.position[0]) ** 2
                + (agent.position[1] - other.position[1]) ** 2
            )
            if dist <= agent.communication_radius:
                result.append(other)
        return result

    @staticmethod
    def _is_agent_active(agent: Agent) -> bool:
        return bool(getattr(agent, "active", True))
