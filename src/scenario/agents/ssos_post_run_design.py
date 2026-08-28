"""Post-run ECLSS design agent — separate from in-sim actors."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.agents.memory import TeamMemoryStore
from core.agents.persona import (
    PersonaAgent,
    TeamConfig,
    build_personas,
    eclss_design_proposal_contract,
    load_team,
    message_contract,
    run_parallel,
)
from core.agents.types import AgentMessage, DeliberationPhase
from core.llm.base import LLMClient
from core.llm.factory import build_llm_client
from scenario.ssos_eclss_loop.design_proposals import (
    DESIGN_DOMAIN,
    SSOS_PROPOSABLE_CHANGE_KINDS,
    build_design_proposals_from_run,
    overlay_auto_applied_changes,
    proposal_covers_prior,
    validate_ssos_proposal_change,
)


@dataclass
class ActorTeamSnapshot:
    agent_ids: List[str] = field(default_factory=list)
    mode: str = "none"
    state: Dict[str, Any] = field(default_factory=dict)
    discourse: List[AgentMessage] = field(default_factory=list)
    policy: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DesignReviewBundle:
    summary: Dict[str, Any]
    scenario_config: Dict[str, Any]
    baseline_graph: Dict[str, Any]
    policy: Dict[str, Any]
    actor_snapshot: Optional[ActorTeamSnapshot] = None
    prior_changes: List[Dict[str, Any]] = field(default_factory=list)
    accumulated_history: List[Dict[str, Any]] = field(default_factory=list)
    strict: bool = False


def post_run_message_step(summary: Dict[str, Any]) -> int:
    """Last 0-based simulation step (``0 .. steps-1``).

    Designer messages must land on a telemetry step so dashboard replay
    (bounded by telemetry min/max) can show them.
    """
    steps = int(summary.get("steps", 0) or 0)
    return max(steps - 1, 0)


class PostRunDesignAgent:
    """Homogeneous designer team invoked only after the simulation loop."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mode = config.get("mode", "none")
        self.llm_mode = self.mode == "llm"
        self.llm_client = self._build_llm_client(config.get("llm", {})) if self.llm_mode else None
        team_cfg = dict(config)
        team_raw = dict(team_cfg.get("team") or {})
        team_raw.setdefault("id_prefix", "eclss_designer")
        team_raw.setdefault("count", 4)
        team_cfg["team"] = team_raw
        self.team_cfg: TeamConfig = load_team(team_cfg)
        self.personas = build_personas(self.team_cfg)
        self.memory_store = TeamMemoryStore(
            agent_ids=list(self.personas.keys()),
            memory_limit=int(config.get("memory_limit", 8)),
            discourse_window=int(config.get("discourse_window", 12)),
        )
        self.agents: Dict[str, PersonaAgent] = {
            agent_id: PersonaAgent(
                persona=persona,
                memory=self.memory_store.agent_memories[agent_id],
                llm_client=self.llm_client,
            )
            for agent_id, persona in self.personas.items()
        }

    def propose(self, bundle: DesignReviewBundle) -> Dict[str, Any]:
        baseline_graph = dict(bundle.baseline_graph or {})
        if self.llm_mode:
            return self._llm_propose(bundle, baseline_graph)
        proposed_by = self.team_cfg.agent_ids[0] if self.team_cfg.agent_ids else "eclss_designer_1"
        proposals = build_design_proposals_from_run(
            proposed_by=proposed_by,
            decision_source="rule",
            policy=bundle.policy,
            summary=bundle.summary,
            baseline_graph=baseline_graph or None,
        )
        if bundle.prior_changes:
            proposals["changes"] = overlay_auto_applied_changes(
                bundle.prior_changes,
                list(proposals.get("changes") or []),
            )
        covers, missing = proposal_covers_prior(
            list(proposals.get("changes") or []),
            bundle.prior_changes,
        )
        proposals["coverage_complete"] = covers
        proposals["coverage_missing"] = missing
        proposals["deliberation_messages"] = [
            AgentMessage(
                step=post_run_message_step(bundle.summary),
                from_role=proposed_by,
                to_role="team",
                message=str(proposals.get("message") or ""),
                message_type="comment",
                reasoning=str(proposals.get("reasoning") or ""),
                metadata={
                    "decision_source": "rule",
                    "deliberation_phase": DeliberationPhase.POST_RUN,
                },
            ).to_dict()
        ]
        return proposals

    def _rep_id(self, summary: Dict[str, Any]) -> str:
        # Designers are a separate team from actors. Labeled always uses
        # designer[0] as the rule speaker. LLM rotates on the *designer* roster
        # using the final step index — not TeamConfig.action_rep_index, which
        # addresses in-sim actors.
        steps = post_run_message_step(summary)
        index = steps % self.team_cfg.count
        return self.team_cfg.agent_ids[index]

    def _llm_propose(
        self,
        bundle: DesignReviewBundle,
        baseline_graph: Dict[str, Any],
    ) -> Dict[str, Any]:
        situation = build_llm_post_run_situation(bundle)
        contract = message_contract()
        step = post_run_message_step(bundle.summary)
        actor_discourse = list((bundle.actor_snapshot.discourse if bundle.actor_snapshot else [])[-8:])
        turns = run_parallel(
            [
                self._deliberation_turn(
                    agent_id=agent_id,
                    step=step,
                    situation=situation,
                    team_discourse=actor_discourse,
                    contract=contract,
                )
                for agent_id in self.team_cfg.agent_ids
            ]
        )
        step_discourse: List[AgentMessage] = []
        for agent_id, parsed in zip(self.team_cfg.agent_ids, turns):
            if parsed is None:
                continue
            step_discourse.append(
                AgentMessage(
                    step=step,
                    from_role=agent_id,
                    to_role="team",
                    message=str(parsed.data.get("message", "")),
                    message_type="comment",
                    reasoning=str(parsed.data.get("reasoning", "")),
                    metadata={
                        "decision_source": "llm",
                        "deliberation_phase": DeliberationPhase.DELIBERATION,
                    },
                )
            )

        rep = self._rep_id(bundle.summary)
        design_contract = eclss_design_proposal_contract()
        agent = self.agents[rep]
        ctx = agent.build_context(
            step=step,
            phase=DeliberationPhase.POST_RUN,
            situation=situation,
            step_discourse=step_discourse,
            team_discourse=actor_discourse + step_discourse,
        )
        parsed = agent.deliberate(
            ctx,
            design_contract,
            PersonaAgent.phase_hint(DeliberationPhase.POST_RUN),
            ("message", "reasoning", "changes"),
        )
        if parsed is None:
            if bundle.strict:
                return {
                    "design_domain": DESIGN_DOMAIN,
                    "proposed_by": rep,
                    "decision_source": "llm_parse_fail",
                    "message": "LLM response could not be parsed.",
                    "reasoning": "LLM response could not be parsed; strict mode skips rule fallback.",
                    "changes": [],
                    "baseline_graph": baseline_graph,
                    "coverage_complete": True,
                    "coverage_missing": [],
                    "parse_notes": ["llm_parse_fail"],
                    "deliberation_messages": [msg.to_dict() for msg in step_discourse]
                    + [
                        AgentMessage(
                            step=step,
                            from_role=rep,
                            to_role="team",
                            message="LLM response could not be parsed.",
                            message_type="comment",
                            reasoning="Strict mode: no rule fallback.",
                            metadata={
                                "decision_source": "llm_parse_fail",
                                "deliberation_phase": DeliberationPhase.POST_RUN,
                            },
                        ).to_dict()
                    ],
                }
            fallback = build_design_proposals_from_run(
                proposed_by=rep,
                decision_source="llm_parse_fail",
                policy=bundle.policy,
                summary=bundle.summary,
                message="LLM response could not be parsed; fell back to rule proposals.",
                baseline_graph=baseline_graph or None,
            )
            fallback["reasoning"] = "LLM response could not be parsed."
            fallback["deliberation_messages"] = [
                msg.to_dict() for msg in step_discourse
            ] + [
                AgentMessage(
                    step=step,
                    from_role=rep,
                    to_role="team",
                    message=str(fallback.get("message") or ""),
                    message_type="comment",
                    reasoning="LLM response could not be parsed; using rule fallback.",
                    metadata={
                        "decision_source": "llm_parse_fail",
                        "deliberation_phase": DeliberationPhase.POST_RUN,
                    },
                ).to_dict()
            ]
            if bundle.prior_changes:
                fallback["changes"] = overlay_auto_applied_changes(
                    bundle.prior_changes,
                    list(fallback.get("changes") or []),
                )
            covers, missing = proposal_covers_prior(
                list(fallback.get("changes") or []),
                bundle.prior_changes,
            )
            fallback["coverage_complete"] = covers
            fallback["coverage_missing"] = missing
            return fallback

        # Keep valid items even in iterate (bundle.strict). All-or-none parse
        # discarded mixed LLM output — typical models emit graph_rewire or a
        # bad set_parameter next to a usable action_profile.
        changes, parse_notes = parse_llm_design_proposals(
            parsed.data.get("changes", []),
            strict=False,
        )
        if _should_overlay_llm_changes(changes, parse_notes, strict=bundle.strict):
            if bundle.prior_changes:
                changes = overlay_auto_applied_changes(
                    bundle.prior_changes,
                    changes,
                )
        covers, missing = proposal_covers_prior(changes, bundle.prior_changes)
        return {
            "design_domain": DESIGN_DOMAIN,
            "proposed_by": rep,
            "decision_source": "llm",
            "message": str(parsed.data.get("message", "")),
            "reasoning": str(parsed.data.get("reasoning", "")),
            "changes": changes,
            "baseline_graph": baseline_graph,
            "parse_status": parsed.status,
            "parse_error": parsed.error,
            "parse_notes": parse_notes,
            "coverage_complete": covers,
            "coverage_missing": missing,
            "raw_response_excerpt": parsed.raw_excerpt,
            "deliberation_messages": [msg.to_dict() for msg in step_discourse]
            + [
                AgentMessage(
                    step=step,
                    from_role=rep,
                    to_role="team",
                    message=str(parsed.data.get("message", "")),
                    message_type="comment",
                    reasoning=str(parsed.data.get("reasoning", "")),
                    metadata={
                        "decision_source": "llm",
                        "deliberation_phase": DeliberationPhase.POST_RUN,
                    },
                ).to_dict()
            ],
        }

    async def _deliberation_turn(
        self,
        *,
        agent_id: str,
        step: int,
        situation: str,
        team_discourse: List[AgentMessage],
        contract: str,
    ):
        agent = self.agents[agent_id]
        ctx = agent.build_context(
            step=step,
            phase=DeliberationPhase.DELIBERATION,
            situation=situation,
            step_discourse=[],
            team_discourse=team_discourse,
        )
        return await agent.deliberate_async(
            ctx,
            contract,
            PersonaAgent.phase_hint(DeliberationPhase.DELIBERATION),
            ("message", "reasoning"),
        )

    @staticmethod
    def _build_llm_client(llm_cfg: Dict[str, Any]) -> LLMClient:
        return build_llm_client(llm_cfg)


def parse_llm_design_proposals(
    raw_changes: Any,
    *,
    strict: bool = False,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Accept valid proposable changes. One representative may emit any count.

    ``strict=True`` rejects the whole list when any proposable item is invalid
    (all-or-none). ``graph_rewire`` is never accepted; it only adds a note.
    """
    if not isinstance(raw_changes, list):
        return [], ["changes is not a list"]
    accepted: List[Dict[str, Any]] = []
    notes: List[str] = []
    blocking = False
    for item in raw_changes:
        if not isinstance(item, dict):
            notes.append("change item is not an object")
            blocking = True
            continue
        change_kind = str(item.get("change_kind", "")).strip()
        payload = item.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        if change_kind not in SSOS_PROPOSABLE_CHANGE_KINDS:
            notes.append(f"unsupported change_kind: {change_kind}")
            if change_kind != "graph_rewire":
                blocking = True
            continue
        if validate_ssos_proposal_change(change_kind, payload) is None:
            notes.append(f"invalid payload for {change_kind}")
            blocking = True
            continue
        accepted.append({"change_kind": change_kind, "payload": payload})
    if strict and blocking:
        return [], notes
    return accepted, notes


def _should_overlay_llm_changes(
    changes: List[Dict[str, Any]],
    parse_notes: List[str],
    *,
    strict: bool,
) -> bool:
    """Overlay prior auto-applied fields unless strict validation emptied the list."""
    if not strict:
        return True
    if changes:
        return True
    blocking_notes = [
        note
        for note in parse_notes
        if note != "unsupported change_kind: graph_rewire"
    ]
    return not blocking_notes


def build_llm_post_run_situation(bundle: DesignReviewBundle) -> str:
    summary = bundle.summary
    sim = bundle.scenario_config.get("simulation") or {}
    thresholds = bundle.scenario_config.get("thresholds") or {}
    snapshot = bundle.actor_snapshot
    telemetry_summary = (
        f"steps={summary.get('steps')}, peak_co2_storage_kg={summary.get('peak_co2_storage_kg')}, "
        f"min_o2_storage_kg={summary.get('min_o2_storage_kg')}, "
        f"final_co2_storage_kg={summary.get('final_co2_storage_kg')}, "
        f"final_o2_storage_kg={summary.get('final_o2_storage_kg')}, "
        f"operational_command_count={summary.get('operational_command_count')}, "
        f"ars_invoked_step={summary.get('ars_invoked_step')}, "
        f"ogs_invoked_step={summary.get('ogs_invoked_step')}, "
        f"co2_requested_step={summary.get('co2_requested_step')}"
    )
    initials = (
        f"initial_co2_storage_kg={sim.get('initial_co2_storage_kg')}, "
        f"initial_o2_storage_kg={sim.get('initial_o2_storage_kg')}, "
        f"initial_product_water_l={sim.get('initial_product_water_l')}"
    )
    # Thresholds are supervision stubs for context — not a pass/fail verdict.
    req_stubs = json.dumps(thresholds, ensure_ascii=False)
    final_health = json.dumps(summary.get("final_health") or {}, ensure_ascii=False)
    actor_state = json.dumps(snapshot.state if snapshot else {}, ensure_ascii=False, default=str)
    discourse = snapshot.discourse if snapshot else []
    discourse_lines = (
        "\n".join(f"- {msg.from_role}: {msg.message}" for msg in discourse[-8:]) or "(none)"
    )
    graph = json.dumps(bundle.baseline_graph, ensure_ascii=False)
    history = json.dumps(bundle.accumulated_history or [], ensure_ascii=False)
    crew = (
        f"crew_initial={summary.get('crew_initial')}, "
        f"crew_remaining={summary.get('crew_remaining')}, "
        f"crew_lost={summary.get('crew_lost')}, "
        f"crew_lost_by_cause={json.dumps(summary.get('crew_lost_by_cause') or {}, ensure_ascii=False)}"
    )
    failures = (
        f"inject_failures={summary.get('inject_failures')}, "
        f"failure_events={summary.get('subsystem_failure_event_count', summary.get('failure_event_count'))}"
    )
    return (
        "Post-run SSOS graph design review. Simulation complete. "
        "Do not judge verification pass/fail. "
        "One representative emits changes; include as many proposals as needed "
        "(no count cap).\n"
        "This is controller-policy adaptation (action_profile / service_config), "
        "not a hardware topology redesign. "
        "set_parameter is a requirement-change suggestion and will not be auto-applied. "
        "If crew_lost > 0, changes must be a non-empty list of valid objects — "
        "do not put the proposal only in message/reasoning. "
        "The next run applies only the changes list you emit now; restate every "
        "prior auto-applied action_profile field and service_config.\n\n"
        f"### Initial conditions\n{initials}\n\n"
        f"### Verification requirement stubs (frozen; do not auto-apply changes)\n{req_stubs}\n\n"
        f"### Occupant survival (objective)\n{crew}\n\n"
        f"### Failures\n{failures}\n\n"
        f"### Telemetry\n{telemetry_summary}\n\n"
        f"### World state\n{final_health}\n\n"
        f"### Actor final state\n{actor_state}\n\n"
        f"### Actor discourse (recent)\n{discourse_lines}\n\n"
        f"### Prior design changes (accumulated)\n{history}\n\n"
        f"Baseline ssos_graph at run end: {graph}"
    )


def actor_snapshot_from_team(team: Any) -> ActorTeamSnapshot:
    state = asdict(team.state) if hasattr(team, "state") else {}
    discourse = []
    if getattr(team, "memory_store", None) is not None:
        discourse = list(team.memory_store.discourse.recent())
    return ActorTeamSnapshot(
        agent_ids=list(getattr(team.team_cfg, "agent_ids", [])),
        mode=str(getattr(team, "mode", "none")),
        state=state,
        discourse=discourse,
        policy=dict(getattr(team, "policy", {}) or {}),
    )
