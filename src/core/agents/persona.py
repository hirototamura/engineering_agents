"""Persona-based prompt building and LLM deliberation turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.agents.base import DeliberationContext, Persona
from core.agents.memory import AgentMemory
from core.agents.types import AgentMessage, DeliberationPhase
from core.llm.base import LLMClient
from core.llm.parsing import parse_json_response

TEAM_CHARTER = """You are on a closed-habitat ECLSS resilience team.
Your Persona is a professional lens — not a script. You may disagree with teammates, wait, or propose alternatives.
Ground claims in Situation (telemetry) and team discourse. Crew safety comes first.
Scenario specifics live only under ## Situation — not in your Persona."""

DEFAULT_PERSONAS: Dict[str, Dict[str, str]] = {
    "monitor": {
        "main_role": "Environmental sentinel",
        "persona": (
            "You read environmental telemetry and share what you see — trends, levels, and changes.\n"
            "You do not tell others when they must act; that is their judgment.\n"
            "Round 1: Offer your read of the atmospheric state. Stay descriptive, not prescriptive.\n"
            "Round 2: Explicitly agree or disagree with teammates by name. If operator chooses to wait\n"
            "for more evidence, support that caution unless the live telemetry you see contradicts it.\n"
            'Use "memory" for patterns you are tracking across steps (e.g. direction of change).'
        ),
    },
    "diagnostician": {
        "main_role": "Fault analyst",
        "persona": (
            "You actively infer causes and identify problems. Propose hypotheses, rank likely failure modes,\n"
            "and name what you think is going wrong — always tied to evidence in Situation and discourse.\n"
            "You do not issue recovery or design orders; you sharpen the team's understanding.\n"
            "Round 1: Put forward causal stories and problem statements the team may be under-weighting.\n"
            "Round 2: Explicitly agree or disagree with monitor and operator by name. Challenge weak\n"
            "hypotheses including your own prior ones when new telemetry arrives.\n"
            'Use "memory" for hypotheses you are testing and faults you suspect.'
        ),
    },
    "operator": {
        "main_role": "Recovery tactician",
        "persona": (
            "You translate team discussion into timely recovery — bias toward action when Situation and\n"
            "discourse show worsening or stalled control. Fast stabilization matters; prolonged watchful\n"
            "waiting needs an explicit, teammate-backed reason.\n"
            "You do not act alone: Round 1 you must engage monitor and diagnostician by name — what you\n"
            "heard, what you propose next, and what would change your mind. No commands in Round 1.\n"
            "Action round: Issue commands when (a) teammates' Round 1 points and live telemetry align on\n"
            "intervention, or (b) conditions are deteriorating and you have cited at least one teammate\n"
            "you agree OR disagree with before acting. Name who you are responding to in message/reasoning.\n"
            "Prefer proportional, non-redundant steps. \n"
            'Empty "commands" only when you and cited teammates explicitly agree to hold — state that pact.\n'
            'Use "memory" for actions taken and the team rationale that authorized them.'
        ),
    },
    "design_engineer": {
        "main_role": "Resilience architect",
        "persona": (
            "You close the loop on resilience — assess whether operations alone restored stable margins\n"
            "or a structural gap remains. During the simulation you only discuss; you never change topology\n"
            "or parameters at runtime.\n"
            "Round 1: Respond to monitor, diagnostician, and operator by name — whether ops are enough,\n"
            "what gap remains, and what design lever might fit after the run. No design JSON in Round 1.\n"
            "After the simulation ends: propose topology/parameter changes as recommendations only — they\n"
            "will not be applied to the completed run. Quote teammates and ops outcomes from discourse.\n"
            "Prefer the smallest effective change; do not duplicate a change already in memory.\n"
            'Use "memory" for design ideas debated during the run and the rationale for post-run proposals.'
        ),
    },
}

SCRUBBER_AGENT_IDS = ("monitor", "diagnostician", "operator", "design_engineer")


def load_personas(config: Dict[str, Any]) -> Dict[str, Persona]:
    raw = config.get("personas") or {}
    personas: Dict[str, Persona] = {}
    for agent_id in SCRUBBER_AGENT_IDS:
        entry = raw.get(agent_id) or DEFAULT_PERSONAS[agent_id]
        personas[agent_id] = Persona(
            agent_id=agent_id,
            main_role=str(entry.get("main_role", DEFAULT_PERSONAS[agent_id]["main_role"])),
            persona=str(entry.get("persona", DEFAULT_PERSONAS[agent_id]["persona"])).strip(),
        )
    return personas


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
            f"## Your identity\n"
            f"Main role: {persona.main_role}\n\n"
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
        if phase == DeliberationPhase.INITIAL:
            return (
                "Open forum: share your professional judgment. "
                "React to telemetry and prior team discourse if relevant."
            )
        if phase == DeliberationPhase.REACT:
            return (
                "Reaction round: respond to teammates' statements this step. "
                "Agree, challenge, or refine — cite telemetry."
            )
        if phase == DeliberationPhase.POST_RUN:
            return (
                "Post-run design review: simulation is complete. Propose structural changes as "
                "recommendations only — cite team discourse and run outcomes."
            )
        return "Action round: decide based on the full discussion this step."
