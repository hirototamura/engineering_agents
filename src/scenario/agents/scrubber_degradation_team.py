"""
Scrubber degradation agent team — rule-based labeled mode + persona LLM guarded mode.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.agents.base import Team
from core.agents.memory import TeamMemoryStore
from core.agents.persona import (
    PersonaAgent,
    design_proposal_contract,
    load_personas,
    message_contract,
    operator_action_contract,
)
from core.agents.types import (
    AgentMessage,
    AgentObservation,
    DeliberationPhase,
    StepAgentOutcome,
)
from core.llm.ollama import OllamaClient
from environment.protocol import (
    CommandKind,
    DesignChange,
    DesignChangeKind,
    HealthStatus,
    RecoveryCommand,
    SimulatorProtocol,
)

ROUND1_SPEAKERS: Tuple[Tuple[str, str, str], ...] = (
    ("monitor", "team", "alert"),
    ("diagnostician", "operator", "diagnosis"),
    ("operator", "team", "assessment"),
    ("design_engineer", "team", "assessment"),
)
ROUND2_SPEAKERS: Tuple[Tuple[str, str, str], ...] = (
    ("monitor", "team", "alert"),
    ("diagnostician", "operator", "diagnosis"),
)


@dataclass
class ScrubberTeamState:
    fan_boost_applied: bool = False
    bypass_enabled: bool = False
    load_reduced: bool = False
    design_assessment_sent: bool = False
    alert_sent: bool = False
    eps_boost_requested: bool = False


class ScrubberDegradationTeam(Team):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mode = config.get("mode", "labeled")
        self.state = ScrubberTeamState()
        roles = config.get("roles", {})
        self.monitor_cfg = roles.get("monitor", {})
        self.diagnostician_cfg = roles.get("diagnostician", {})
        self.operator_cfg = roles.get("operator", {})
        self.design_cfg = roles.get("design_engineer", {})
        self.llm_mode = self.mode == "labeled_llm"
        self.llm_enabled = self.llm_mode
        self.llm_client = self._build_llm_client(config.get("llm", {})) if self.llm_enabled else None

        self.personas = load_personas(config)
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

    def run_step(self, sim: SimulatorProtocol, obs: AgentObservation) -> StepAgentOutcome:
        if self.llm_mode:
            outcome = self._run_step_llm(sim, obs)
            self.memory_store.commit_step(outcome)
            return outcome
        outcome = StepAgentOutcome()
        outcome.messages.extend(self._monitor(obs))
        outcome.messages.extend(self._diagnostician(obs))
        op_msgs, op_cmds = self._operator(obs)
        outcome.messages.extend(op_msgs)
        outcome.commands.extend(op_cmds)
        outcome.messages.extend(self._design_engineer_discourse(obs))
        return outcome

    def apply_outcome(self, sim: SimulatorProtocol, outcome: StepAgentOutcome) -> None:
        for cmd in outcome.commands:
            sim.apply_command(cmd)
        for change in outcome.design_changes:
            sim.apply_design_change(change)

    def _run_step_llm(
        self,
        sim: SimulatorProtocol,
        obs: AgentObservation,
    ) -> StepAgentOutcome:
        outcome = StepAgentOutcome()
        step_discourse: List[AgentMessage] = []
        situation = self._situation_context(obs, self.monitor_cfg, self.design_cfg, self.operator_cfg)

        for agent_id, to_role, message_type in ROUND1_SPEAKERS:
            msg = self._llm_deliberation_turn(
                obs=obs,
                agent_id=agent_id,
                to_role=to_role,
                message_type=message_type,
                phase=DeliberationPhase.INITIAL,
                situation=situation,
                step_discourse=step_discourse,
                contract=message_contract(),
                required=("message",),
            )
            if msg is not None:
                outcome.messages.append(msg)
                step_discourse.append(msg)
            else:
                outcome.messages.append(
                    self._llm_skip(
                        obs=obs,
                        agent_id=agent_id,
                        phase=DeliberationPhase.INITIAL,
                        reason="parse_failed_or_empty_message",
                        decision_source="llm_parse_fail",
                    )
                )

        for agent_id, to_role, message_type in ROUND2_SPEAKERS:
            msg = self._llm_deliberation_turn(
                obs=obs,
                agent_id=agent_id,
                to_role=to_role,
                message_type=message_type,
                phase=DeliberationPhase.REACT,
                situation=situation,
                step_discourse=step_discourse,
                contract=message_contract(),
                required=("message",),
            )
            if msg is not None:
                outcome.messages.append(msg)
                step_discourse.append(msg)
            else:
                outcome.messages.append(
                    self._llm_skip(
                        obs=obs,
                        agent_id=agent_id,
                        phase=DeliberationPhase.REACT,
                        reason="parse_failed_or_empty_message",
                        decision_source="llm_parse_fail",
                    )
                )

        op_msgs, op_cmds = self._llm_operator_action(obs, situation, step_discourse)
        outcome.messages.extend(op_msgs)
        outcome.commands.extend(op_cmds)
        return outcome

    def propose_post_run_design(
        self,
        sim: SimulatorProtocol,
        summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        baseline = sim.get_design_state().to_dict()
        if self.llm_mode:
            return self._llm_post_run_design_proposal(summary, baseline)
        return self._rule_post_run_design_proposal(summary, baseline)

    def _llm_deliberation_turn(
        self,
        *,
        obs: AgentObservation,
        agent_id: str,
        to_role: str,
        message_type: str,
        phase: str,
        situation: str,
        step_discourse: List[AgentMessage],
        contract: str,
        required: tuple[str, ...],
    ) -> Optional[AgentMessage]:
        agent = self.agents[agent_id]
        ctx = agent.build_context(
            step=obs.step,
            phase=phase,
            situation=situation,
            step_discourse=step_discourse,
            team_discourse=self.memory_store.discourse.recent(),
        )
        parsed = agent.deliberate(
            ctx,
            contract,
            PersonaAgent.phase_hint(phase),
            required,
        )
        if parsed is None:
            return None
        message = str(parsed.data.get("message", "")).strip()
        if not message:
            return None
        persona = self.personas[agent_id]
        metadata: Dict[str, Any] = {
            "decision_source": "llm",
            "deliberation_phase": phase,
            "main_role": persona.main_role,
            "parse_status": parsed.status,
            "parse_error": parsed.error,
            "raw_response_excerpt": parsed.raw_excerpt,
        }
        llm_memory = parsed.data.get("memory")
        if llm_memory:
            metadata["llm_memory"] = str(llm_memory)
        return AgentMessage(
            step=obs.step,
            from_role=agent_id,
            to_role=to_role,
            message=message,
            message_type=message_type,
            reasoning=str(parsed.data.get("reasoning", "")),
            metadata=metadata,
        )

    def _llm_operator_action(
        self,
        obs: AgentObservation,
        situation: str,
        step_discourse: List[AgentMessage],
    ) -> Tuple[List[AgentMessage], List[RecoveryCommand]]:
        contract = operator_action_contract()
        agent = self.agents["operator"]
        ctx = agent.build_context(
            step=obs.step,
            phase=DeliberationPhase.ACTION,
            situation=situation,
            step_discourse=step_discourse,
            team_discourse=self.memory_store.discourse.recent(),
        )
        parsed = agent.deliberate(
            ctx,
            contract,
            "Issue recovery commands when discourse and Situation warrant intervention; "
            "cite named teammates from Round 1. ",
            ("commands",),
        )
        if parsed is None:
            return [
                self._llm_skip(
                    obs=obs,
                    agent_id="operator",
                    phase=DeliberationPhase.ACTION,
                    reason="parse_failed",
                    decision_source="llm_parse_fail",
                )
            ], []

        message = parsed.data.get("message", "Operator assessed current state.")
        reasoning = parsed.data.get("reasoning", "")
        commands: List[RecoveryCommand] = []
        parse_notes: List[str] = []
        raw_commands = parsed.data.get("commands", [])
        if not isinstance(raw_commands, list):
            raw_commands = []

        for item in raw_commands:
            cmd, note = self._parse_llm_operator_command(item)
            if note:
                parse_notes.append(note)
            if cmd is not None:
                commands.append(cmd)

        persona = self.personas["operator"]
        base_meta: Dict[str, Any] = {
            "decision_source": "llm",
            "deliberation_phase": DeliberationPhase.ACTION,
            "main_role": persona.main_role,
            "parse_status": parsed.status,
            "parse_error": parsed.error,
            "raw_response_excerpt": parsed.raw_excerpt,
            "parse_notes": parse_notes,
        }
        if parsed.data.get("memory"):
            base_meta["llm_memory"] = str(parsed.data["memory"])

        if not commands:
            return [
                self._llm_skip(
                    obs=obs,
                    agent_id="operator",
                    phase=DeliberationPhase.ACTION,
                    reason="empty_commands",
                    decision_source="llm_no_action",
                    parse_status=parsed.status,
                    parse_error=parsed.error,
                )
            ], []

        llm_msg = AgentMessage(
            step=obs.step,
            from_role="operator",
            to_role="team",
            message=str(message),
            message_type="recovery_command",
            reasoning=str(reasoning),
            metadata=base_meta,
        )
        return [llm_msg], commands

    def _llm_post_run_design_proposal(
        self,
        summary: Dict[str, Any],
        baseline: Dict[str, Any],
    ) -> Dict[str, Any]:
        steps = int(summary.get("steps", 0))
        situation = (
            "Post-run design review. Simulation complete.\n"
            f"Run summary: steps={steps}, peak_co2_ppm={summary.get('peak_co2_ppm')}, "
            f"final_co2_ppm={summary.get('final_co2_ppm')}, "
            f"co2_recovered_below_threshold_step={summary.get('co2_recovered_below_threshold_step')}, "
            f"anomaly_seen={summary.get('anomaly_seen')}, "
            f"eps_boost_applied_step={summary.get('eps_boost_applied_step')}.\n"
            f"Baseline topology at run end: {json.dumps(baseline.get('topology', {}), ensure_ascii=False)}"
        )
        contract = design_proposal_contract()
        agent = self.agents["design_engineer"]
        ctx = agent.build_context(
            step=steps,
            phase=DeliberationPhase.POST_RUN,
            situation=situation,
            step_discourse=[],
            team_discourse=self.memory_store.discourse.recent(),
        )
        parsed = agent.deliberate(
            ctx,
            contract,
            PersonaAgent.phase_hint(DeliberationPhase.POST_RUN),
            ("message", "reasoning", "changes"),
        )
        if parsed is None:
            return {
                "proposed_by": "design_engineer",
                "decision_source": "llm_parse_fail",
                "message": "",
                "reasoning": "LLM response could not be parsed.",
                "changes": [],
                "baseline_topology": baseline.get("topology", {}),
            }

        changes, parse_notes = self._parse_llm_design_proposals(parsed.data.get("changes", []))
        return {
            "proposed_by": "design_engineer",
            "decision_source": "llm",
            "message": str(parsed.data.get("message", "")),
            "reasoning": str(parsed.data.get("reasoning", "")),
            "changes": changes,
            "baseline_topology": baseline.get("topology", {}),
            "parse_status": parsed.status,
            "parse_error": parsed.error,
            "parse_notes": parse_notes,
            "raw_response_excerpt": parsed.raw_excerpt,
        }

    def _rule_post_run_design_proposal(
        self,
        summary: Dict[str, Any],
        baseline: Dict[str, Any],
    ) -> Dict[str, Any]:
        co2_threshold = float(self.design_cfg.get("co2_threshold_ppm", 1000))
        peak = float(summary.get("peak_co2_ppm", 0))
        anomaly_seen = bool(summary.get("anomaly_seen"))
        if peak < co2_threshold and not anomaly_seen:
            return {
                "proposed_by": "design_engineer",
                "decision_source": "rule",
                "message": "No structural topology changes recommended after this run.",
                "reasoning": (
                    f"Peak CO2 {peak:.0f} ppm stayed below design review threshold "
                    f"{co2_threshold:.0f} ppm with no sustained anomaly."
                ),
                "changes": [],
                "baseline_topology": baseline.get("topology", {}),
            }

        edge = self.design_cfg.get("bypass_edge", {})
        changes = [
            {
                "change_kind": "add_edge",
                "payload": {
                    "node_a": edge.get("node_a", "manifold"),
                    "node_b": edge.get("node_b", "scrubber"),
                    "kind": edge.get("kind", "bypass"),
                },
            }
        ]
        return {
            "proposed_by": "design_engineer",
            "decision_source": "rule",
            "message": "Propose permanent bypass plumbing between manifold and scrubber.",
            "reasoning": (
                "Repeated anomaly and high CO2 during the run; temporary ops may be insufficient "
                "for long-term resilience."
            ),
            "changes": changes,
            "baseline_topology": baseline.get("topology", {}),
        }

    def _parse_llm_design_proposals(
        self,
        raw_changes: Any,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        if not isinstance(raw_changes, list):
            return [], ["changes is not a list"]
        accepted: List[Dict[str, Any]] = []
        notes: List[str] = []
        for item in raw_changes:
            if not isinstance(item, dict):
                notes.append("change item is not an object")
                continue
            change_kind = str(item.get("change_kind", "")).strip()
            payload = item.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}
            if self._parse_llm_design_change(change_kind=change_kind, payload=payload) is None:
                notes.append(f"unparsed change: {change_kind}")
                continue
            accepted.append({"change_kind": change_kind, "payload": payload})
        return accepted, notes

    def _llm_skip(
        self,
        *,
        obs: AgentObservation,
        agent_id: str,
        phase: str,
        reason: str,
        decision_source: str,
        **extra: Any,
    ) -> AgentMessage:
        persona = self.personas.get(agent_id)
        metadata: Dict[str, Any] = {
            "decision_source": decision_source,
            "deliberation_phase": phase,
            "skip_reason": reason,
        }
        if persona is not None:
            metadata["main_role"] = persona.main_role
        metadata.update(extra)
        return AgentMessage(
            step=obs.step,
            from_role=agent_id,
            to_role="team",
            message="",
            message_type="skip",
            reasoning=reason,
            metadata=metadata,
        )

    @staticmethod
    def _attach_metadata(
        messages: List[AgentMessage],
        metadata: Dict[str, Any],
    ) -> List[AgentMessage]:
        for message in messages:
            merged = dict(message.metadata)
            merged.update(metadata)
            message.metadata = merged
        return messages

    @staticmethod
    def _coerce_boolean(value: Any) -> Tuple[Optional[bool], Optional[str]]:
        if isinstance(value, bool):
            return value, None
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized == "true":
                return True, None
            if normalized in {"false", "0", "no"}:
                return False, None
        return None, 'value must be boolean or "true"/"false" string'

    def _parse_llm_operator_command(self, item: Any) -> Tuple[Optional[RecoveryCommand], Optional[str]]:
        """Parse LLM operator JSON into a command without team-level policy guards."""
        if not isinstance(item, dict):
            return None, "operator command is not an object"
        kind = str(item.get("kind", "")).strip()
        value = item.get("value")
        if kind == "set_fan_speed":
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return None, "invalid fan speed value"
            return (
                RecoveryCommand(kind=CommandKind.SET_FAN_SPEED, value=numeric, issued_by="operator"),
                None,
            )
        if kind == "enable_bypass":
            coerced, coerce_error = self._coerce_boolean(value)
            if coerce_error is not None:
                return None, coerce_error
            return (
                RecoveryCommand(kind=CommandKind.ENABLE_BYPASS, value=coerced, issued_by="operator"),
                None,
            )
        if kind == "reduce_load":
            coerced, coerce_error = self._coerce_boolean(value)
            if coerce_error is not None:
                return None, coerce_error
            return (
                RecoveryCommand(kind=CommandKind.REDUCE_LOAD, value=coerced, issued_by="operator"),
                None,
            )
        if kind == "request_eps_boost":
            try:
                watts = float(value)
            except (TypeError, ValueError):
                return None, "eps boost value must be numeric"
            return (
                RecoveryCommand(kind=CommandKind.REQUEST_EPS_BOOST, value=watts, issued_by="operator"),
                None,
            )
        return None, f"unsupported operator command kind: {kind}"

    def _parse_llm_design_change(self, change_kind: str, payload: Dict[str, Any]) -> Optional[DesignChange]:
        """Parse LLM design JSON into a change without team-level policy guards."""
        if change_kind == "add_node":
            node_id = str(payload.get("id", "")).strip()
            if not node_id:
                return None
            return DesignChange(
                kind=DesignChangeKind.ADD_NODE,
                payload={
                    "id": node_id,
                    "name": str(payload.get("name", node_id)),
                    "kind": str(payload.get("kind", "volume")),
                },
                proposed_by="design_engineer",
            )
        if change_kind == "add_edge":
            node_a = payload.get("node_a")
            node_b = payload.get("node_b")
            if not node_a or not node_b:
                return None
            return DesignChange(
                kind=DesignChangeKind.ADD_EDGE,
                payload={
                    "node_a": node_a,
                    "node_b": node_b,
                    "kind": payload.get("kind", "bypass"),
                },
                proposed_by="design_engineer",
            )
        if change_kind == "set_parameter":
            key = str(payload.get("key", "")).strip()
            if not key:
                return None
            try:
                value = float(payload.get("value"))
            except (TypeError, ValueError):
                return None
            return DesignChange(
                kind=DesignChangeKind.SET_PARAMETER,
                payload={"key": key, "value": value},
                proposed_by="design_engineer",
            )
        return None

    @staticmethod
    def _build_llm_client(llm_cfg: Dict[str, Any]) -> OllamaClient:
        return OllamaClient(
            base_url=str(llm_cfg.get("base_url", "http://localhost:11434")),
            model=str(llm_cfg.get("model", "llama3.2")),
            temperature=float(llm_cfg.get("temperature", 0.45)),
            max_tokens=int(llm_cfg.get("max_tokens", 512)),
            repeat_penalty=float(llm_cfg.get("repeat_penalty", 1.1)),
            repeat_last_n=int(llm_cfg.get("repeat_last_n", 128)),
            min_p=float(llm_cfg.get("min_p", 0.05)),
            think=llm_cfg.get("think", False),
            api_timeout=int(llm_cfg.get("api_timeout", 10)),
        )

    @staticmethod
    def _rule_metadata() -> Dict[str, Any]:
        return {"decision_source": "rule"}

    @staticmethod
    def _situation_context(
        obs: AgentObservation,
        monitor_cfg: Dict[str, Any],
        design_cfg: Dict[str, Any],
        operator_cfg: Dict[str, Any],
    ) -> str:
        """Scenario briefing + live telemetry — kept separate from persona definitions."""
        alert_ppm = float(monitor_cfg.get("co2_alert_ppm", 900))
        recovery_ppm = float(operator_cfg.get("co2_recovery_ppm", 1000))
        design_min_step = int(design_cfg.get("min_step", 35))
        design_co2 = float(design_cfg.get("co2_threshold_ppm", 1000))
        mission = (
            "Scenario: scrubber_degradation. Closed-habitat ECLSS ops. "
            "Anomaly may reduce scrubber efficiency and increase CO2 load; "
            "power margin may shrink. Rule thresholds (for reference): "
            f"monitor alert {alert_ppm:.0f} ppm, recovery band {recovery_ppm:.0f} ppm, "
            f"design engineer reviews topology post-run when peak CO2 >= {design_co2:.0f} ppm "
            f"(reference threshold from step {design_min_step})."
        )
        telemetry = (
            f"step={obs.step}, co2_ppm={obs.telemetry.co2_ppm:.2f}, "
            f"scrubber_efficiency={obs.telemetry.scrubber_efficiency:.4f}, "
            f"power_margin_w={obs.telemetry.power_margin_w:.2f}, "
            f"fan_speed={obs.telemetry.fan_speed:.2f}, bypass_enabled={obs.telemetry.bypass_enabled}, "
            f"load_reduced={obs.telemetry.load_reduced}, anomaly_flags={obs.telemetry.anomaly_flags}, "
            f"co2_status={obs.health.co2_status.value}, power_status={obs.health.power_status.value}"
        )
        return f"{mission}\nTelemetry: {telemetry}"

    def _monitor(self, obs: AgentObservation) -> List[AgentMessage]:
        threshold = float(self.monitor_cfg.get("co2_alert_ppm", 900))
        if obs.telemetry.co2_ppm < threshold:
            return []
        msg = (
            f"CO2 at {obs.telemetry.co2_ppm:.0f} ppm exceeds alert threshold {threshold:.0f}."
        )
        self.state.alert_sent = True
        return [
            AgentMessage(
                step=obs.step,
                from_role="monitor",
                to_role="team",
                message=msg,
                message_type="alert",
                reasoning="Telemetry threshold crossed.",
                metadata=self._rule_metadata(),
            )
        ]

    def _diagnostician(self, obs: AgentObservation) -> List[AgentMessage]:
        flags = obs.telemetry.anomaly_flags
        if not flags:
            return []
        eff = obs.telemetry.scrubber_efficiency
        msg = (
            f"Active anomalies: {', '.join(flags)}. "
            f"Scrubber efficiency {eff:.2f}; suspect degradation with rising cabin load."
        )
        return [
            AgentMessage(
                step=obs.step,
                from_role="diagnostician",
                to_role="operator",
                message=msg,
                message_type="diagnosis",
                reasoning="Anomaly flags present in telemetry.",
                metadata=self._rule_metadata(),
            )
        ]

    def _operator(self, obs: AgentObservation) -> tuple[List[AgentMessage], List[RecoveryCommand]]:
        messages: List[AgentMessage] = []
        commands: List[RecoveryCommand] = []
        recovery_ppm = float(self.operator_cfg.get("co2_recovery_ppm", 1000))

        if obs.telemetry.co2_ppm >= recovery_ppm and not self.state.fan_boost_applied:
            fan = float(self.operator_cfg.get("fan_speed", 1.0))
            commands.append(
                RecoveryCommand(kind=CommandKind.SET_FAN_SPEED, value=fan, issued_by="operator")
            )
            self.state.fan_boost_applied = True
            messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role="operator",
                    to_role="team",
                    message=f"Increasing fan speed to {fan} to boost scrub rate.",
                    message_type="recovery_command",
                    reasoning=f"CO2 {obs.telemetry.co2_ppm:.0f} ppm >= {recovery_ppm:.0f}.",
                    metadata=self._rule_metadata(),
                )
            )

        if (
            self.operator_cfg.get("reduce_load_on_power_critical", True)
            and obs.health.power_status == HealthStatus.CRITICAL
            and not self.state.load_reduced
        ):
            commands.append(
                RecoveryCommand(kind=CommandKind.REDUCE_LOAD, value=True, issued_by="operator")
            )
            self.state.load_reduced = True
            messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role="operator",
                    to_role="team",
                    message="Reducing cabin metabolic load to lower CO2 production.",
                    message_type="recovery_command",
                    reasoning="Power margin critical; load shedding.",
                    metadata=self._rule_metadata(),
                )
            )

        if (
            self.operator_cfg.get("request_eps_boost_on_power_critical", True)
            and obs.health.power_status == HealthStatus.CRITICAL
            and obs.telemetry.eps_support_steps_remaining == 0
        ):
            eps_boost_w = float(self.operator_cfg.get("eps_boost_w", 120.0))
            commands.append(
                RecoveryCommand(kind=CommandKind.REQUEST_EPS_BOOST, value=eps_boost_w, issued_by="operator")
            )
            self.state.eps_boost_requested = True
            messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role="operator",
                    to_role="team",
                    message=f"Requesting EPS support boost of {eps_boost_w:.0f} W.",
                    message_type="recovery_command",
                    reasoning="Power margin critical; requesting temporary EPS assist.",
                    metadata=self._rule_metadata(),
                )
            )

        if (
            self.operator_cfg.get("enable_bypass", True)
            and obs.telemetry.co2_ppm >= recovery_ppm
            and self.state.fan_boost_applied
            and not self.state.bypass_enabled
        ):
            commands.append(
                RecoveryCommand(kind=CommandKind.ENABLE_BYPASS, value=True, issued_by="operator")
            )
            self.state.bypass_enabled = True
            messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role="operator",
                    to_role="team",
                    message="Enabling temporary bypass flow to increase scrub throughput.",
                    message_type="recovery_command",
                    reasoning="Fan boost insufficient; engaging bypass.",
                    metadata=self._rule_metadata(),
                )
            )

        return messages, commands

    def _design_engineer_discourse(self, obs: AgentObservation) -> List[AgentMessage]:
        if self.state.design_assessment_sent:
            return []

        min_step = int(self.design_cfg.get("min_step", 35))
        co2_threshold = float(self.design_cfg.get("co2_threshold_ppm", 1000))
        if obs.step < min_step or obs.telemetry.co2_ppm < co2_threshold:
            return []

        self.state.design_assessment_sent = True
        return [
            AgentMessage(
                step=obs.step,
                from_role="design_engineer",
                to_role="team",
                message=(
                    "Ops may stabilize CO2 short-term; a durable bypass path should be evaluated "
                    "after this run."
                ),
                message_type="assessment",
                reasoning="High CO2 with anomaly — structural relief may be needed post-simulation.",
                metadata=self._rule_metadata(),
            )
        ]
