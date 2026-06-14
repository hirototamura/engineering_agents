"""SSOS ECLSS loop agent team — operates EclssBackend instead of Mock ECLSS simulator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.agents.memory import TeamMemoryStore
from core.agents.persona import TeamConfig, build_personas, load_team
from core.agents.types import AgentMessage
from core.llm.ollama import OllamaClient
from environment.ssos.eclss_backend import EclssBackend
from environment.ssos.eclss_types import ArsGoal, OgsGoal
from scenario.agents.eclss_loop_types import (
    EclssLoopObservation,
    EclssOperationalCommand,
    StepEclssOutcome,
)


@dataclass
class EclssLoopTeamState:
    alert_sent: bool = False
    ars_invoked: bool = False
    co2_requested: bool = False
    ogs_invoked: bool = False


class SsosEclssLoopTeam:
    """Crew Simulation replacement — sends ARS/OGS goals and O2/CO2 service calls."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mode = config.get("mode", "labeled_rule_base")
        self.state = EclssLoopTeamState()
        self.llm_mode = self.mode == "llm"
        self.llm_client = self._build_llm_client(config.get("llm", {})) if self.llm_mode else None

        self.team_cfg: TeamConfig = load_team(config)
        self.personas = build_personas(self.team_cfg)
        self.policy: Dict[str, Any] = (
            config.get("policy", {}) if self.mode == "labeled_rule_base" else {}
        )

        self.memory_store = TeamMemoryStore(
            agent_ids=list(self.personas.keys()),
            memory_limit=int(config.get("memory_limit", 8)),
            discourse_window=int(config.get("discourse_window", 12)),
        )

    def run_step(self, obs: EclssLoopObservation) -> StepEclssOutcome:
        if self.llm_mode:
            return self._run_step_llm(obs)
        return self._run_step_labeled(obs)

    def apply_outcome(self, backend: EclssBackend, outcome: StepEclssOutcome) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for cmd in outcome.commands:
            event = self._apply_command(backend, cmd)
            if event is not None:
                events.append(event)
        return events

    def _run_step_labeled(self, obs: EclssLoopObservation) -> StepEclssOutcome:
        outcome = StepEclssOutcome()
        rep = self.team_cfg.action_rep_id(obs.step)
        agent_ids = self.team_cfg.agent_ids
        n = len(agent_ids)
        co2_high = float(self.policy.get("co2_storage_high_kg", 1500.0))
        o2_low = float(self.policy.get("o2_storage_low_kg", 450.0))
        co2 = obs.telemetry.co2_storage_kg
        o2 = obs.telemetry.o2_storage_kg

        if co2 is not None and co2 >= co2_high and not self.state.alert_sent:
            commenter = agent_ids[obs.step % n]
            self.state.alert_sent = True
            outcome.messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role=commenter,
                    to_role="team",
                    message=(
                        f"CO2 storage {co2:.1f} kg exceeds high band {co2_high:.1f} kg."
                    ),
                    message_type="alert",
                    reasoning="Storage telemetry threshold crossed.",
                    metadata=self._rule_metadata(),
                )
            )

        failures = [
            name
            for name, flag in (
                ("ars", obs.telemetry.ars_failure_enabled),
                ("ogs", obs.telemetry.ogs_failure_enabled),
                ("wrs", obs.telemetry.wrs_failure_enabled),
            )
            if flag
        ]
        if failures:
            commenter = agent_ids[(obs.step + 1) % n]
            outcome.messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role=commenter,
                    to_role="team",
                    message=f"Subsystem failure flags active: {', '.join(failures)}.",
                    message_type="diagnosis",
                    reasoning="Self-diagnosis topics report failure injection.",
                    metadata=self._rule_metadata(),
                )
            )

        messages, commands = self._labeled_recovery(obs, rep, co2_high, o2_low, co2, o2)
        outcome.messages.extend(messages)
        outcome.commands.extend(commands)
        return outcome

    def _labeled_recovery(
        self,
        obs: EclssLoopObservation,
        rep: str,
        co2_high: float,
        o2_low: float,
        co2: Optional[float],
        o2: Optional[float],
    ) -> Tuple[List[AgentMessage], List[EclssOperationalCommand]]:
        messages: List[AgentMessage] = []
        commands: List[EclssOperationalCommand] = []

        if co2 is not None and co2 >= co2_high and not self.state.ars_invoked:
            ars_payload = dict(self.policy.get("ars_goal", {}))
            commands.append(
                EclssOperationalCommand(
                    kind="air_revitalisation",
                    payload=ars_payload,
                    issued_by=rep,
                )
            )
            self.state.ars_invoked = True
            messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role=rep,
                    to_role="team",
                    message="Starting ARS air_revitalisation to vent CO2 from storage.",
                    message_type="operational_command",
                    reasoning=f"CO2 storage {co2:.1f} kg >= {co2_high:.1f} kg.",
                    metadata=self._rule_metadata(),
                )
            )

        if o2 is not None and o2 <= o2_low and not self.state.ogs_invoked:
            if self.policy.get("request_co2_before_ogs", True) and not self.state.co2_requested:
                amount = float(self.policy.get("request_co2_amount", 25.0))
                commands.append(
                    EclssOperationalCommand(
                        kind="request_co2",
                        payload={"amount": amount},
                        issued_by=rep,
                    )
                )
                self.state.co2_requested = True
                messages.append(
                    AgentMessage(
                        step=obs.step,
                        from_role=rep,
                        to_role="team",
                        message=f"Requesting {amount:.1f} kg CO2 feedstock for Sabatier (OGS).",
                        message_type="operational_command",
                        reasoning=f"O2 storage {o2:.1f} kg <= {o2_low:.1f} kg.",
                        metadata=self._rule_metadata(),
                    )
                )

            ogs_payload = dict(self.policy.get("ogs_goal", {}))
            commands.append(
                EclssOperationalCommand(
                    kind="oxygen_generation",
                    payload=ogs_payload,
                    issued_by=rep,
                )
            )
            self.state.ogs_invoked = True
            messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role=rep,
                    to_role="team",
                    message="Starting OGS oxygen_generation cycle.",
                    message_type="operational_command",
                    reasoning=f"O2 storage {o2:.1f} kg <= {o2_low:.1f} kg.",
                    metadata=self._rule_metadata(),
                )
            )

        return messages, commands

    def _run_step_llm(self, obs: EclssLoopObservation) -> StepEclssOutcome:
        # LLM path deferred — labeled_rule_base is the regression baseline for Phase 4.
        return StepEclssOutcome(
            messages=[
                AgentMessage(
                    step=obs.step,
                    from_role=self.team_cfg.action_rep_id(obs.step),
                    to_role="team",
                    message="",
                    message_type="skip",
                    reasoning="llm mode not implemented for ssos_eclss_loop in Phase 4",
                    metadata={"decision_source": "llm_not_implemented"},
                )
            ]
        )

    def _apply_command(
        self,
        backend: EclssBackend,
        cmd: EclssOperationalCommand,
    ) -> Optional[Dict[str, Any]]:
        kind = cmd.kind
        payload = cmd.payload
        if kind == "air_revitalisation":
            result = backend.send_air_revitalisation_goal(ArsGoal(**payload))
        elif kind == "oxygen_generation":
            result = backend.send_oxygen_generation_goal(OgsGoal(**payload))
        elif kind == "request_co2":
            result = backend.request_co2(float(payload["amount"]))
        elif kind == "request_o2":
            result = backend.request_o2(float(payload["amount"]))
        elif kind == "set_subsystem_failure":
            backend.set_subsystem_failure(str(payload["subsystem"]), bool(payload["enabled"]))
            return {
                "kind": "/eclss/events/operational_applied",
                "command": cmd.to_dict(),
                "message": f"failure flag {payload['subsystem']}={payload['enabled']}",
            }
        else:
            return {
                "kind": "/eclss/events/operational_rejected",
                "command": cmd.to_dict(),
                "message": f"unsupported command kind: {kind}",
            }

        return {
            "kind": "/eclss/events/operational_applied",
            "command": cmd.to_dict(),
            "result": result.to_dict(),
            "message": getattr(result, "summary_message", None) or getattr(result, "message", ""),
        }

    @staticmethod
    def _rule_metadata() -> Dict[str, Any]:
        return {"decision_source": "rule"}

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
