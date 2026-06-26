"""Persona-based prompt building and LLM deliberation turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.agents.base import DeliberationContext, Persona
from core.agents.memory import AgentMemory
from core.agents.types import AgentMessage, DeliberationPhase
from core.llm.base import LLMClient
from core.llm.parsing import parse_json_response

TEAM_CHARTER = """You are on a closed-habitat ECLSS resilience team.
Your Persona is a professional lens — not a script. You may disagree with teammates, wait, or propose alternatives.
Ground claims in Telemetry (numbers) and World state (descriptive health). Normative safety judgment is yours as an ECLSS engineer — do not assume hidden facility thresholds.
Scenario specifics live only under ## Situation — not in your Persona."""

DEFAULT_TEAM_PERSONA = (
    "Closed-habitat ECLSS colleague engineer. Ground observations in Telemetry and World state; "
    "state hypotheses and recovery options from team discourse.\n"
    "Do not change topology during the simulation — structural changes are post-run recommendations only.\n"
    "Cite teammates by agent_id; agree or disagree explicitly."
)


@dataclass(frozen=True)
class TeamConfig:
    count: int
    id_prefix: str
    shared_persona: str
    agent_ids: Tuple[str, ...]

    def action_rep_index(self, step: int) -> int:
        return (step - 1) % self.count

    def action_rep_id(self, step: int) -> str:
        return self.agent_ids[self.action_rep_index(step)]


def load_team(config: Dict[str, Any]) -> TeamConfig:
    team_raw = config.get("team") or {}
    count = max(1, int(team_raw.get("count", 4)))
    id_prefix = str(team_raw.get("id_prefix", "engineer"))
    persona_text = str(team_raw.get("persona") or DEFAULT_TEAM_PERSONA).strip()
    agent_ids = tuple(f"{id_prefix}_{i}" for i in range(1, count + 1))
    return TeamConfig(
        count=count,
        id_prefix=id_prefix,
        shared_persona=persona_text,
        agent_ids=agent_ids,
    )


def build_personas(team: TeamConfig) -> Dict[str, Persona]:
    return {
        agent_id: Persona(agent_id=agent_id, persona=team.shared_persona)
        for agent_id in team.agent_ids
    }


@dataclass
class ParsedTurn:
    data: Dict[str, Any]
    status: str
    error: Optional[str] = None
    raw_excerpt: str = ""


MESSAGE_WORD_LIMIT = 60
REASONING_WORD_LIMIT = 80
MEMORY_WORD_LIMIT = 25


def json_envelope_preamble() -> str:
    return (
        "Return ONLY one valid JSON object (multi-line is allowed). "
        "No markdown. No code fences. No prose outside JSON. "
    )


def output_word_limits_clause() -> str:
    return (
        f'Keep "message" at most {MESSAGE_WORD_LIMIT} words and '
        f'"reasoning" at most {REASONING_WORD_LIMIT} words. '
        f'Optional "memory" at most {MEMORY_WORD_LIMIT} words.'
    )


def message_contract() -> str:
    return (
        f"{json_envelope_preamble()}"
        'Required keys: "message", "reasoning". '
        'Optional key: "memory". '
        f"{output_word_limits_clause()} "
        'Example: {"message":"CO2 rising.","reasoning":"co2_ppm crossed threshold",'
        '"memory":"Fan boost may be next."}'
    )


def operator_action_contract() -> str:
    return (
        f"{json_envelope_preamble()}"
        'Required keys: "message", "reasoning", "commands". '
        'Optional key: "memory". '
        f"{output_word_limits_clause()} "
        'commands must be a list of {"kind": "...", "value": ...} with kind in '
        '["set_fan_speed","enable_bypass","reduce_load","request_eps_boost"]. '
        "Empty commands when you and teammates agree to hold this step."
    )


def design_proposal_contract() -> str:
    return (
        f"{json_envelope_preamble()}"
        'Required keys: "message", "reasoning", "changes". '
        'Optional key: "memory". '
        f"{output_word_limits_clause()} "
        '"changes" is a list of {"change_kind","payload"} objects. '
        'change_kind in ["add_node","add_edge","set_parameter"]. '
        'add_node payload: {"id","name","kind"}. '
        'add_edge payload: {"node_a","node_b","kind"}. '
        'set_parameter payload: {"key","value"}. '
        "Proposals are post-run only — they will NOT be applied to the completed simulation."
    )


def eclss_operational_action_contract() -> str:
    return (
        f"{json_envelope_preamble()}"
        'Required keys: "message", "reasoning", "commands". '
        'Optional key: "memory". '
        f"{output_word_limits_clause()} "
        '"commands" is a list of {"kind","payload"} objects. '
        'kind in ["air_revitalisation","oxygen_generation","request_co2","request_o2"]. '
        'air_revitalisation payload fields: initial_co2_mass, initial_moisture_content, '
        'initial_contaminants (numeric). '
        'oxygen_generation payload fields: input_water_mass, iodine_concentration (numeric). '
        'request_co2 / request_o2 payload: {"amount": <kg>}. '
        "Empty commands when you and teammates agree to hold this step."
    )


def eclss_design_proposal_contract() -> str:
    return (
        f"{json_envelope_preamble()}"
        'Required keys: "message", "reasoning", "changes". '
        'Optional key: "memory". '
        f"{output_word_limits_clause()} "
        '"changes" is a list of {"change_kind","payload"} objects. '
        'change_kind in ["action_profile","service_config","set_parameter","graph_rewire"]. '
        'action_profile payload: {"subsystem":"ars|ogs|wrs","action":"...","fields":{...}}. '
        'service_config payload: {"service":"request_co2|request_o2", ...}. '
        'set_parameter payload: {"target":"dotted.config.path","value":...}. '
        "graph_rewire payload: ROS remapping manifest for the next launch. "
        "Proposals are post-run only — they will NOT be applied during this simulation."
    )


def design_action_contract() -> str:
    """Deprecated alias — runtime design actions are no longer applied."""
    return design_proposal_contract()


def format_discourse(messages: List[AgentMessage]) -> str:
    if not messages:
        return "(none yet)"
    lines = []
    for msg in messages:
        phase = msg.metadata.get("deliberation_phase", "")
        prefix = f"[{phase}] " if phase else ""
        lines.append(f"- {prefix}{msg.from_role}: {msg.message}")
    return "\n".join(lines)


def format_memory(entries: List[str]) -> str:
    if not entries:
        return "(empty — first steps of the mission)"
    return "\n".join(f"- {entry}" for entry in entries)


class PersonaPromptBuilder:
    @staticmethod
    def build(
        persona: Persona,
        ctx: DeliberationContext,
        contract: str,
        action_hint: str,
        charter: str = TEAM_CHARTER,
    ) -> str:
        return (
            f"{charter}\n\n"
            f"agent_id: {persona.agent_id}\n"
            f"phase: {ctx.phase}\n\n"
            f"## How you think and act\n"
            f"{persona.persona}\n\n"
            f"## Situation\n"
            f"{ctx.situation}\n\n"
            f"## Team discourse (recent team messages)\n"
            f"{format_discourse(ctx.team_discourse)}\n\n"
            f"## Your memory (what you recall from prior steps)\n"
            f"{format_memory(ctx.agent_memory)}\n\n"
            f"## This step so far\n"
            f"{format_discourse(ctx.step_discourse)}\n\n"
            f"## Your task\n"
            f"{action_hint}\n\n"
            f"## Output contract\n"
            f"{contract}\n"
        )


class PersonaAgent:
    def __init__(
        self,
        persona: Persona,
        memory: AgentMemory,
        llm_client: LLMClient | None = None,
    ):
        self.persona = persona
        self.memory = memory
        self.llm_client = llm_client

    def build_context(
        self,
        *,
        step: int,
        phase: str,
        situation: str,
        step_discourse: List[AgentMessage],
        team_discourse: List[AgentMessage],
    ) -> DeliberationContext:
        return DeliberationContext(
            step=step,
            phase=phase,
            situation=situation,
            step_discourse=step_discourse,
            team_discourse=team_discourse,
            agent_memory=self.memory.recent(),
        )

    def deliberate(
        self,
        ctx: DeliberationContext,
        contract: str,
        action_hint: str,
        required: tuple[str, ...],
    ) -> Optional[ParsedTurn]:
        prompt = PersonaPromptBuilder.build(
            self.persona,
            ctx,
            contract,
            action_hint,
        )
        raw = ""
        if self.llm_client is not None:
            raw = self.llm_client.generate(prompt)
        parsed = parse_json_response(raw, required=required)
        if parsed.status in {"fallback", "empty_response"}:
            return None
        return ParsedTurn(
            data=parsed.data,
            status=parsed.status,
            error=parsed.error,
            raw_excerpt=parsed.raw_excerpt,
        )

    @staticmethod
    def phase_hint(phase: str) -> str:
        if phase == DeliberationPhase.DELIBERATION:
            return (
                "Deliberation: share observations and professional judgment. "
                "React to Telemetry, World state, and teammates by agent_id."
            )
        if phase == DeliberationPhase.POST_RUN:
            return (
                "Post-run design review: simulation is complete. Propose structural changes as "
                "recommendations only — cite team discourse and run outcomes."
            )
        return (
            "Action round (team representative): issue recovery commands when discourse and "
            "Situation warrant intervention; cite named teammates from this step."
        )
