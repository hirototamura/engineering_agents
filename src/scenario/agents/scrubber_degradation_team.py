"""
Rule-based agent team for scrubber_degradation only.

Four human-assigned role labels (Monitor, Diagnostician, Operator, DesignEngineer).
Not a generic role framework — see memo/backlog.md BL-001 for unlabeled Base Role research.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
        self.state = ScrubberTeamState()
        roles = config.get("roles", {})
        self.monitor_cfg = roles.get("monitor", {})
        self.diagnostician_cfg = roles.get("diagnostician", {})
        self.operator_cfg = roles.get("operator", {})
        self.design_cfg = roles.get("design_engineer", {})

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
        return outcome

    def apply_outcome(self, sim: MockEclssSimulator, outcome: StepAgentOutcome) -> None:
        for cmd in outcome.commands:
            sim.apply_command(cmd)
        for change in outcome.design_changes:
            sim.apply_design_change(change)

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
        )
        return [msg], [change]
