"""
Rule-based agent team for scrubber_degradation only.

Four human-assigned role labels (Monitor, Diagnostician, Operator, DesignEngineer).
Not a generic role framework — see memo/backlog.md BL-001 for unlabeled Base Role research.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.llm.ollama import OllamaClient
from core.llm.parsing import parse_json_response
from environment.protocol import (
    CommandKind,
    DesignChange,
    DesignChangeKind,
    HealthStatus,
    RecoveryCommand,
    SimulatorProtocol,
)
from scenario.agents.types import AgentMessage, AgentObservation, StepAgentOutcome


@dataclass
class ScrubberTeamState:
    fan_boost_applied: bool = False
    bypass_enabled: bool = False
    load_reduced: bool = False
    design_change_applied: bool = False
    alert_sent: bool = False
    eps_boost_requested: bool = False


class ScrubberDegradationTeam:
    """Scenario-specific labeled roles for the scrubber degradation demo."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mode = config.get("mode", "labeled")
        self.state = ScrubberTeamState()
        roles = config.get("roles", {})
        self.monitor_cfg = roles.get("monitor", {})
        self.diagnostician_cfg = roles.get("diagnostician", {})
        self.operator_cfg = roles.get("operator", {})
        self.design_cfg = roles.get("design_engineer", {})
        self.llm_shadow = self.mode == "labeled_shadow"
        self.llm_guarded = self.mode == "labeled_llm_guarded"
        self.llm_enabled = self.llm_shadow or self.llm_guarded
        self.llm_client = self._build_llm_client(config.get("llm", {})) if self.llm_enabled else None

    def run_step(self, sim: SimulatorProtocol, obs: AgentObservation) -> StepAgentOutcome:
        if self.llm_guarded:
            return self._run_step_llm_guarded(sim, obs)
        outcome = StepAgentOutcome()
        outcome.messages.extend(self._monitor(obs))
        outcome.messages.extend(self._diagnostician(obs))
        op_msgs, op_cmds = self._operator(obs)
        outcome.messages.extend(op_msgs)
        outcome.commands.extend(op_cmds)
        des_msgs, des_changes = self._design_engineer(obs)
        outcome.messages.extend(des_msgs)
        outcome.design_changes.extend(des_changes)
        if self.llm_shadow:
            outcome.messages.extend(self._llm_shadow_messages(obs))
        return outcome

    def apply_outcome(self, sim: SimulatorProtocol, outcome: StepAgentOutcome) -> None:
        for cmd in outcome.commands:
            sim.apply_command(cmd)
        for change in outcome.design_changes:
            sim.apply_design_change(change)

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

    def _run_step_llm_guarded(
        self,
        sim: SimulatorProtocol,
        obs: AgentObservation,
    ) -> StepAgentOutcome:
        outcome = StepAgentOutcome()

        monitor_msg = self._llm_role_message(
            obs=obs,
            role="monitor",
            to_role="team",
            message_type="alert",
        )
        if monitor_msg is not None:
            outcome.messages.append(monitor_msg)
        else:
            fallback = self._monitor(obs)
            outcome.messages.extend(self._attach_metadata(fallback, {"decision_source": "rule_fallback"}))

        diagnosis_msg = self._llm_role_message(
            obs=obs,
            role="diagnostician",
            to_role="operator",
            message_type="diagnosis",
        )
        if diagnosis_msg is not None:
            outcome.messages.append(diagnosis_msg)
        else:
            fallback = self._diagnostician(obs)
            outcome.messages.extend(self._attach_metadata(fallback, {"decision_source": "rule_fallback"}))

        op_msgs, op_cmds = self._llm_operator(obs)
        outcome.messages.extend(op_msgs)
        outcome.commands.extend(op_cmds)

        design_msgs, design_changes = self._llm_design_engineer_guarded(sim, obs)
        outcome.messages.extend(design_msgs)
        outcome.design_changes.extend(design_changes)
        return outcome

    def _llm_role_message(
        self,
        obs: AgentObservation,
        role: str,
        to_role: str,
        message_type: str,
    ) -> Optional[AgentMessage]:
        contract = self._shadow_output_contract()
        prompt = (
            f"Role: {role} in ECLSS scrubber_degradation. "
            f"{contract} "
            f"Telemetry: {self._telemetry_context(obs)}"
        )
        parsed = self._parse_llm(prompt=prompt, required=("message",))
        if parsed is None:
            return None
        message = parsed.data.get("message", "").strip()
        if not message:
            return None
        return AgentMessage(
            step=obs.step,
            from_role=role,
            to_role=to_role,
            message=message,
            message_type=message_type,
            reasoning=parsed.data.get("reasoning", ""),
            metadata={
                "decision_source": "llm",
                "parse_status": parsed.status,
                "parse_error": parsed.error,
                "raw_response_excerpt": parsed.raw_excerpt,
            },
        )

    def _llm_operator(self, obs: AgentObservation) -> Tuple[List[AgentMessage], List[RecoveryCommand]]:
        contract = (
            "Return ONLY one valid JSON object (multi-line is allowed). "
            "No markdown. No code fences. No prose outside JSON. "
            'Required keys: "message", "reasoning", "commands". '
            'commands must be a list of {"kind": "...", "value": ...} with kind in '
            '["set_fan_speed","enable_bypass","reduce_load","request_eps_boost"].'
        )
        prompt = (
            "Role: operator in ECLSS scrubber_degradation. "
            f"{contract} Telemetry: {self._telemetry_context(obs)}"
        )
        parsed = self._parse_llm(prompt=prompt, required=("commands",))
        if parsed is None:
            fallback_msgs, fallback_cmds = self._operator(obs)
            return self._attach_metadata(fallback_msgs, {"decision_source": "rule_fallback"}), fallback_cmds

        message = parsed.data.get("message", "Operator assessed current state.")
        reasoning = parsed.data.get("reasoning", "")
        commands: List[RecoveryCommand] = []
        guard_notes: List[str] = []
        raw_commands = parsed.data.get("commands", [])
        if not isinstance(raw_commands, list):
            raw_commands = []

        for item in raw_commands:
            cmd, note = self._guard_operator_command(item)
            if note:
                guard_notes.append(note)
            if cmd is not None:
                commands.append(cmd)

        if not commands:
            fallback_msgs, fallback_cmds = self._operator(obs)
            fallback_meta = {
                "decision_source": "rule_fallback",
                "parse_status": parsed.status,
                "parse_error": parsed.error,
                "raw_response_excerpt": parsed.raw_excerpt,
                "guard_notes": guard_notes,
            }
            return self._attach_metadata(fallback_msgs, fallback_meta), fallback_cmds

        llm_msg = AgentMessage(
            step=obs.step,
            from_role="operator",
            to_role="team",
            message=message,
            message_type="recovery_command",
            reasoning=reasoning,
            metadata={
                "decision_source": "llm",
                "parse_status": parsed.status,
                "parse_error": parsed.error,
                "raw_response_excerpt": parsed.raw_excerpt,
                "guard_notes": guard_notes,
            },
        )
        return [llm_msg], commands

    def _guard_operator_command(self, item: Any) -> Tuple[Optional[RecoveryCommand], Optional[str]]:
        if not isinstance(item, dict):
            return None, "operator command is not an object"
        kind = str(item.get("kind", "")).strip()
        value = item.get("value")
        if kind == "set_fan_speed":
            if self.state.fan_boost_applied:
                return None, "fan speed already set"
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return None, "invalid fan speed value"
            if not (0.0 <= numeric <= 1.0):
                return None, "fan speed out of range"
            self.state.fan_boost_applied = True
            return (
                RecoveryCommand(kind=CommandKind.SET_FAN_SPEED, value=numeric, issued_by="operator"),
                None,
            )
        if kind == "enable_bypass":
            if self.state.bypass_enabled:
                return None, "bypass already enabled"
            if value is not True:
                return None, "bypass value must be literal true boolean"
            self.state.bypass_enabled = True
            return (
                RecoveryCommand(kind=CommandKind.ENABLE_BYPASS, value=True, issued_by="operator"),
                None,
            )
        if kind == "reduce_load":
            if self.state.load_reduced:
                return None, "load already reduced"
            if value is not True:
                return None, "reduce_load value must be literal true boolean"
            self.state.load_reduced = True
            return (
                RecoveryCommand(kind=CommandKind.REDUCE_LOAD, value=True, issued_by="operator"),
                None,
            )
        if kind == "request_eps_boost":
            if self.state.eps_boost_requested:
                return None, "eps boost already requested"
            try:
                watts = float(value)
            except (TypeError, ValueError):
                return None, "eps boost value must be numeric"
            if not (0.0 < watts <= 500.0):
                return None, "eps boost out of range"
            self.state.eps_boost_requested = True
            return (
                RecoveryCommand(kind=CommandKind.REQUEST_EPS_BOOST, value=watts, issued_by="operator"),
                None,
            )
        return None, f"unsupported operator command kind: {kind}"

    def _llm_design_engineer_guarded(
        self,
        sim: SimulatorProtocol,
        obs: AgentObservation,
    ) -> Tuple[List[AgentMessage], List[DesignChange]]:
        if self.state.design_change_applied:
            return [], []

        min_step = int(self.design_cfg.get("min_step", 35))
        co2_threshold = float(self.design_cfg.get("co2_threshold_ppm", 1000))
        if obs.step < min_step or obs.telemetry.co2_ppm < co2_threshold:
            return [], []

        allowed_nodes = {node.id for node in sim.get_topology().nodes}
        allowed_params = set(self.design_cfg.get("allowed_parameters", ["scrubber_base_efficiency"]))
        contract = (
            "Return ONLY one valid JSON object (multi-line is allowed). "
            "No markdown. No code fences. No prose outside JSON. "
            'Required keys: "apply_change", "change_kind", "payload", "message", "reasoning". '
            'change_kind in ["add_edge","set_parameter"].'
        )
        prompt = (
            "Role: design_engineer in ECLSS scrubber_degradation. "
            f"{contract} Telemetry: {self._telemetry_context(obs)}"
        )
        parsed = self._parse_llm(prompt=prompt, required=("apply_change", "change_kind", "payload"))
        if parsed is None:
            fallback_msgs, fallback_changes = self._design_engineer(obs)
            return self._attach_metadata(fallback_msgs, {"decision_source": "rule_fallback"}), fallback_changes

        apply_change = bool(parsed.data.get("apply_change"))
        if not apply_change:
            return [], []
        change_kind = str(parsed.data.get("change_kind", "")).strip()
        payload = parsed.data.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        guarded_change, guard_reason = self._guard_design_change(
            change_kind=change_kind,
            payload=payload,
            allowed_nodes=allowed_nodes,
            allowed_parameters=allowed_params,
        )
        if guarded_change is None:
            reject_msg = AgentMessage(
                step=obs.step,
                from_role="design_engineer",
                to_role="team",
                message="Guard rejected LLM design proposal; keeping current design.",
                message_type="design_guard_reject",
                reasoning=guard_reason or "invalid proposal",
                metadata={
                    "decision_source": "llm_guard_reject",
                    "parse_status": parsed.status,
                    "parse_error": parsed.error,
                    "raw_response_excerpt": parsed.raw_excerpt,
                },
            )
            return [reject_msg], []

        self.state.design_change_applied = True
        apply_msg = AgentMessage(
            step=obs.step,
            from_role="design_engineer",
            to_role="team",
            message=parsed.data.get("message", "Applying guarded design change."),
            message_type="design_change",
            reasoning=parsed.data.get("reasoning", ""),
            metadata={
                "decision_source": "llm",
                "parse_status": parsed.status,
                "parse_error": parsed.error,
                "raw_response_excerpt": parsed.raw_excerpt,
                "guard_reason": guard_reason,
            },
        )
        return [apply_msg], [guarded_change]

    @staticmethod
    def _guard_design_change(
        change_kind: str,
        payload: Dict[str, Any],
        allowed_nodes: set[str],
        allowed_parameters: set[str],
    ) -> Tuple[Optional[DesignChange], Optional[str]]:
        if change_kind == "add_edge":
            node_a = payload.get("node_a")
            node_b = payload.get("node_b")
            if node_a not in allowed_nodes or node_b not in allowed_nodes:
                return None, "edge references unknown node"
            kind = payload.get("kind", "bypass")
            if kind not in {"bypass", "flow"}:
                return None, "edge kind not allowed"
            return (
                DesignChange(
                    kind=DesignChangeKind.ADD_EDGE,
                    payload={"node_a": node_a, "node_b": node_b, "kind": kind},
                    proposed_by="design_engineer",
                ),
                None,
            )
        if change_kind == "set_parameter":
            key = str(payload.get("key", ""))
            if key not in allowed_parameters:
                return None, f"parameter not allowed: {key}"
            try:
                value = float(payload.get("value"))
            except (TypeError, ValueError):
                return None, "parameter value is not numeric"
            if key == "scrubber_base_efficiency" and not (0.1 <= value <= 1.2):
                return None, "scrubber_base_efficiency out of range"
            if key == "bypass_flow_bonus" and not (0.0 <= value <= 1.0):
                return None, "bypass_flow_bonus out of range"
            if key == "load_reduction_factor" and not (0.1 <= value <= 1.0):
                return None, "load_reduction_factor out of range"
            return (
                DesignChange(
                    kind=DesignChangeKind.SET_PARAMETER,
                    payload={"key": key, "value": value},
                    proposed_by="design_engineer",
                ),
                None,
            )
        return None, f"unsupported change_kind: {change_kind}"

    def _parse_llm(self, prompt: str, required: tuple[str, ...]):
        raw = ""
        if self.llm_client is not None:
            raw = self.llm_client.generate(prompt)
        parsed = parse_json_response(raw, required=required)
        if parsed.status in {"fallback", "empty_response"}:
            return None
        return parsed

    @staticmethod
    def _build_llm_client(llm_cfg: Dict[str, Any]) -> OllamaClient:
        return OllamaClient(
            base_url=str(llm_cfg.get("base_url", "http://localhost:11434")),
            model=str(llm_cfg.get("model", "llama3.2")),
            temperature=float(llm_cfg.get("temperature", 0.1)),
            max_tokens=int(llm_cfg.get("max_tokens", 200)),
            repeat_penalty=float(llm_cfg.get("repeat_penalty", 1.1)),
            repeat_last_n=int(llm_cfg.get("repeat_last_n", 128)),
            min_p=float(llm_cfg.get("min_p", 0.05)),
            think=llm_cfg.get("think", False),
            api_timeout=int(llm_cfg.get("api_timeout", 10)),
        )

    @staticmethod
    def _rule_metadata() -> Dict[str, Any]:
        return {"decision_source": "rule"}

    def _telemetry_context(self, obs: AgentObservation) -> str:
        return (
            f"step={obs.step}, co2_ppm={obs.telemetry.co2_ppm:.2f}, "
            f"scrubber_efficiency={obs.telemetry.scrubber_efficiency:.4f}, "
            f"power_margin_w={obs.telemetry.power_margin_w:.2f}, "
            f"fan_speed={obs.telemetry.fan_speed:.2f}, bypass_enabled={obs.telemetry.bypass_enabled}, "
            f"load_reduced={obs.telemetry.load_reduced}, anomaly_flags={obs.telemetry.anomaly_flags}, "
            f"co2_status={obs.health.co2_status.value}, power_status={obs.health.power_status.value}"
        )

    @staticmethod
    def _shadow_output_contract() -> str:
        return (
            "Return ONLY one valid JSON object (multi-line is allowed). "
            "No markdown. No code fences. No prose outside JSON. "
            'Required keys: "message", "reasoning". '
            'Example: {"message":"CO2 rising; boost fan.","reasoning":"co2_ppm crossed threshold"}'
        )

    def _llm_shadow_messages(self, obs: AgentObservation) -> List[AgentMessage]:
        contract = self._shadow_output_contract()
        context = self._telemetry_context(obs)
        prompts = [
            (
                "monitor",
                "team",
                "llm_shadow_monitor",
                ("message",),
                (
                    "Role: monitor in ECLSS scrubber_degradation. "
                    f"{contract} "
                    f"Telemetry: {context}"
                ),
            ),
            (
                "diagnostician",
                "operator",
                "llm_shadow_diagnosis",
                ("message",),
                (
                    "Role: diagnostician in ECLSS scrubber_degradation. "
                    f"{contract} "
                    f"Telemetry: {context}"
                ),
            ),
            (
                "operator",
                "team",
                "llm_shadow_operator",
                ("message",),
                (
                    "Role: operator in ECLSS scrubber_degradation. "
                    f"{contract} "
                    f"Telemetry: {context}"
                ),
            ),
            (
                "design_engineer",
                "team",
                "llm_shadow_design",
                ("message",),
                (
                    "Role: design_engineer in ECLSS scrubber_degradation. "
                    f"{contract} "
                    f"Telemetry: {context}"
                ),
            ),
        ]
        return [
            self._llm_shadow_message(
                obs=obs,
                role=role,
                to_role=to_role,
                message_type=message_type,
                required=required,
                prompt=prompt,
            )
            for role, to_role, message_type, required, prompt in prompts
        ]

    def _llm_shadow_message(
        self,
        obs: AgentObservation,
        role: str,
        to_role: str,
        message_type: str,
        required: tuple[str, ...],
        prompt: str,
    ) -> AgentMessage:
        raw = ""
        if self.llm_client is not None:
            raw = self.llm_client.generate(prompt)
        parsed = parse_json_response(raw, required=required)
        message = parsed.data.get("message", "")
        if not message:
            message = f"[shadow:{role}] no message"
        reasoning = parsed.data.get("reasoning", "")
        return AgentMessage(
            step=obs.step,
            from_role=role,
            to_role=to_role,
            message=message,
            message_type=message_type,
            reasoning=reasoning,
            metadata={
                "decision_source": "llm_shadow",
                "parse_status": parsed.status,
                "parse_error": parsed.error,
                "raw_response_excerpt": parsed.raw_excerpt,
            },
        )

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
            and not self.state.eps_boost_requested
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

    def _design_engineer(self, obs: AgentObservation) -> tuple[List[AgentMessage], List[DesignChange]]:
        if self.state.design_change_applied:
            return [], []

        min_step = int(self.design_cfg.get("min_step", 35))
        co2_threshold = float(self.design_cfg.get("co2_threshold_ppm", 1000))
        if obs.step < min_step or obs.telemetry.co2_ppm < co2_threshold:
            return [], []

        edge = self.design_cfg.get("bypass_edge", {})
        change = DesignChange(
            kind=DesignChangeKind.ADD_EDGE,
            payload={
                "node_a": edge.get("node_a", "manifold"),
                "node_b": edge.get("node_b", "scrubber"),
                "kind": edge.get("kind", "bypass"),
            },
            proposed_by="design_engineer",
        )
        self.state.design_change_applied = True
        msg = AgentMessage(
            step=obs.step,
            from_role="design_engineer",
            to_role="team",
            message="Proposing permanent bypass plumbing between manifold and scrubber.",
            message_type="design_change",
            reasoning="Repeated anomaly; temporary ops insufficient for long-term resilience.",
            metadata=self._rule_metadata(),
        )
        return [msg], [change]
