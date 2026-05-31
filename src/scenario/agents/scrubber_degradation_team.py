"""
Rule-based agent team for scrubber_degradation only.

Four human-assigned role labels (Monitor, Diagnostician, Operator, DesignEngineer).
Not a generic role framework — see memo/backlog.md BL-001 for unlabeled Base Role research.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from core.llm.ollama import OllamaClient
from core.llm.parsing import parse_json_response
from environment.protocol import (
    CommandKind,
    DesignChange,
    DesignChangeKind,
    HealthStatus,
    RecoveryCommand,
)
from environment.ssos.mock_eclss import MockEclssSimulator
from scenario.agents.types import AgentMessage, AgentObservation, StepAgentOutcome


@dataclass
class ScrubberTeamState:
    fan_boost_applied: bool = False
    bypass_enabled: bool = False
    load_reduced: bool = False
    design_change_applied: bool = False
    alert_sent: bool = False


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
        self.llm_client = self._build_llm_client(config.get("llm", {})) if self.llm_shadow else None

    def run_step(self, sim: MockEclssSimulator, obs: AgentObservation) -> StepAgentOutcome:
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

    def apply_outcome(self, sim: MockEclssSimulator, outcome: StepAgentOutcome) -> None:
        for cmd in outcome.commands:
            sim.apply_command(cmd)
        for change in outcome.design_changes:
            sim.apply_design_change(change)

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
