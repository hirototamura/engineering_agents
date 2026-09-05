"""SSOS ECLSS loop agent team — operates EclssBackend instead of Mock ECLSS simulator."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from core.agents.base import Team
from core.agents.memory import TeamMemoryStore
from core.agents.persona import (
    PersonaAgent,
    TeamConfig,
    build_personas,
    eclss_operational_action_contract,
    load_team,
    message_contract,
    run_parallel,
)
from core.agents.types import AgentMessage, DeliberationPhase
from core.llm.base import LLMClient
from core.llm.factory import build_llm_client
from environment.ssos.eclss.backend import EclssBackend
from environment.ssos.eclss.plant_sim.config import PlantConfigError, PlantSimConfig
from environment.ssos.eclss.plant_sim.model import per_interval
from environment.ssos.eclss.plant_sim.stoichiometry import WATER_PER_O2
from environment.ssos.eclss.types import ArsGoal, OgsGoal, WrsGoal
from scenario.agents.eclss_loop_types import (
    EclssLoopObservation,
    EclssOperationalCommand,
    StepEclssOutcome,
)
from scenario.ssos_eclss_loop.health import (
    DEFAULT_CO2_STORAGE_CRITICAL_KG,
    DEFAULT_CO2_STORAGE_HIGH_KG,
    DEFAULT_O2_STORAGE_LOW_KG,
    DEFAULT_PRODUCT_WATER_LOW_L,
)

_ECLSS_OPERATIONAL_KINDS = frozenset(
    {"air_revitalisation", "oxygen_generation", "water_recovery", "request_co2", "request_o2"}
)
_LABELED_SUBSYSTEMS = ("ars", "ogs", "wrs")

# One command per group per step (design doc §7). Subsystem actions and the
# feedstock / withdrawal services are counted separately: `request_co2` is a
# Sabatier service, not a second ARS action, so it has its own slot.
_COMMAND_GROUPS = {
    "air_revitalisation": "ars_action",
    "oxygen_generation": "ogs_action",
    "water_recovery": "wrs_action",
    "request_co2": "request_co2_service",
    "request_o2": "request_o2_service",
}
DUPLICATE_COMMAND_REASON = "duplicate_command_this_step"

_ARS_GOAL_FIELDS = frozenset({"initial_co2_mass", "initial_moisture_content", "initial_contaminants"})
_OGS_GOAL_FIELDS = frozenset({"input_water_mass", "iodine_concentration"})
_WRS_GOAL_FIELDS = frozenset({"urine_volume"})


def _resolve_max_actions_per_step(
    raw: Any, *, team_count: int, clamp_to_team: bool = True
) -> int:
    if isinstance(raw, bool) or raw is None:
        raise ValueError(f"max_actions_per_step must be an integer >= 1, got {raw!r}")
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, float):
        if not raw.is_integer():
            raise ValueError(f"max_actions_per_step must be an integer >= 1, got {raw!r}")
        value = int(raw)
    elif isinstance(raw, str):
        try:
            as_float = float(raw.strip())
        except ValueError as exc:
            raise ValueError(
                f"max_actions_per_step must be an integer >= 1, got {raw!r}"
            ) from exc
        if not as_float.is_integer():
            raise ValueError(f"max_actions_per_step must be an integer >= 1, got {raw!r}")
        value = int(as_float)
    else:
        raise ValueError(f"max_actions_per_step must be an integer >= 1, got {raw!r}")
    if value < 1:
        raise ValueError(f"max_actions_per_step must be >= 1, got {value}")
    if clamp_to_team:
        return min(value, team_count)
    return value


def _finite_reading(value: Optional[float]) -> Optional[float]:
    """Return ``value`` when it is a finite number; otherwise ``None``."""
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _ceil_positive(deficit: float, per_action: float) -> int:
    """How many actions are needed to cover ``deficit``. Zero if already done."""
    if not math.isfinite(deficit) or not math.isfinite(per_action) or deficit <= 0:
        return 0
    return max(1, math.ceil(deficit / max(float(per_action), 1e-9)))


def interleave_labeled_actions(counts: Mapping[str, int], cap: int) -> List[str]:
    """Round-robin ARS → OGS → WRS, repeating each up to its needed count, capped."""
    queue: deque[Tuple[str, int]] = deque()
    for name in _LABELED_SUBSYSTEMS:
        n = int(counts.get(name, 0))
        if n > 0:
            queue.append((name, n))
    slots: List[str] = []
    while queue and len(slots) < cap:
        name, n = queue.popleft()
        slots.append(name)
        if n > 1:
            queue.append((name, n - 1))
    return slots


def _wrs_batches_to_empty(
    urine_l: float,
    grey_l: float,
    *,
    urine_request_l: float,
    max_feed_l: float,
) -> int:
    """How many WRS actions drain the current urine/grey buffers."""
    urine_req = max(float(urine_request_l), 1e-9)
    max_feed = max(float(max_feed_l), urine_req)
    urine = max(0.0, float(urine_l))
    grey = max(0.0, float(grey_l))
    batches = 0
    while (urine > 1e-9 or grey > 1e-9) and batches < 64:
        urine_feed = min(urine_req, urine, max_feed)
        grey_feed = min(grey, max(0.0, max_feed - urine_feed))
        if urine_feed + grey_feed <= 1e-9:
            break
        urine -= urine_feed
        grey -= grey_feed
        batches += 1
    return batches


@dataclass
class EclssLoopTeamState:
    alert_sent: bool = False
    ars_invoked: bool = False
    ars_critical_escalated: bool = False
    co2_requested: bool = False
    ogs_invoked: bool = False
    wrs_invoked: bool = False
    co2_at_ars_dispatch: Optional[float] = None
    o2_at_ogs_dispatch: Optional[float] = None


class SsosEclssLoopTeam(Team):
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
        self.agents: Dict[str, PersonaAgent] = {
            agent_id: PersonaAgent(
                persona=persona,
                memory=self.memory_store.agent_memories[agent_id],
                llm_client=self.llm_client,
            )
            for agent_id, persona in self.personas.items()
        }
        self.max_actions_per_step = _resolve_max_actions_per_step(
            config.get("max_actions_per_step", 1),
            team_count=self.team_cfg.count,
            clamp_to_team=self.mode == "llm",
        )
        self._active_ids: List[str] = list(self.team_cfg.agent_ids)

    @property
    def active_ids(self) -> List[str]:
        return list(self._active_ids)

    def set_crew_alive(self, crew_alive: int) -> List[str]:
        """Shrink the operator roster from the tail to match occupant count.

        Occupants never return. Returns agent ids removed this call.
        """
        n = max(0, min(int(crew_alive), self.team_cfg.count))
        previous = len(self._active_ids)
        if n >= previous:
            return []
        lost_ids = list(self.team_cfg.agent_ids[n:previous])
        self._active_ids = list(self.team_cfg.agent_ids[:n])
        return lost_ids

    def _action_rep_id(self, step: int) -> str:
        """Round-robin representative for 0-based scenario steps (`step % N`)."""
        ids = self._active_ids
        if not ids:
            raise ValueError("no surviving operators")
        return ids[step % len(ids)]

    def _action_rep_ids(self, step: int) -> List[str]:
        """Rotating window of action representatives (length ``max_actions_per_step``)."""
        ids = self._active_ids
        n = len(ids)
        if n == 0:
            return []
        k = min(self.max_actions_per_step, n)
        start = step % n
        return [ids[(start + offset) % n] for offset in range(k)]

    def run_step(self, backend: EclssBackend, obs: EclssLoopObservation) -> StepEclssOutcome:
        _ = backend
        if not self._active_ids:
            return StepEclssOutcome()
        if self.llm_mode:
            outcome = self._run_step_llm(obs)
            self.memory_store.commit_step(outcome)
            return outcome
        return self._run_step_labeled(obs)

    def apply_outcome(self, backend: EclssBackend, outcome: StepEclssOutcome) -> List[Dict[str, Any]]:
        """Apply this step's commands, at most one attempt per subsystem / service.

        The gate is deterministic and mode-independent (labeled, llm, tests):
        the first command of a group takes the group's slot for this step, every
        later one is recorded as ``operational_rejected`` with
        ``reason=duplicate_command_this_step``. The slot is spent on the attempt,
        not on success — a first command the backend rejects (busy subsystem,
        failed subsystem, invalid payload) still blocks the rest of the step, so
        a team cannot retry its way past the limit. ``max_actions_per_step``
        still sizes the action round; this is the execution-side safety net
        (design doc §7).
        """
        events: List[Dict[str, Any]] = []
        used_groups: set[str] = set()
        for cmd in outcome.commands:
            group = _COMMAND_GROUPS.get(cmd.kind)
            if group is not None and group in used_groups:
                events.append(
                    {
                        "kind": "/eclss/events/operational_rejected",
                        "command": cmd.to_dict(),
                        "reason": DUPLICATE_COMMAND_REASON,
                        "message": (
                            f"{cmd.kind} already issued this step "
                            f"(one command per {group} per step)"
                        ),
                    }
                )
                continue
            event = self._apply_command(backend, cmd)
            if group is not None:
                used_groups.add(group)
            if event is not None:
                events.append(event)
        return events

    def _run_step_llm(self, obs: EclssLoopObservation) -> StepEclssOutcome:
        outcome = StepEclssOutcome()
        step_discourse: List[AgentMessage] = []
        situation = build_llm_situation(obs)
        # Simultaneous round: all agents see prior-step team discourse only, so
        # vLLM can batch the N in-flight requests instead of walking the roster.
        team_discourse = self.memory_store.discourse.recent()
        turns = run_parallel(
            [
                self._llm_deliberation_turn(
                    obs=obs,
                    agent_id=agent_id,
                    to_role="team",
                    message_type="comment",
                    phase=DeliberationPhase.DELIBERATION,
                    situation=situation,
                    step_discourse=[],
                    team_discourse=team_discourse,
                    contract=message_contract(),
                    required=("message",),
                )
                for agent_id in self._active_ids
            ]
        )
        for agent_id, msg in zip(self._active_ids, turns):
            if msg is not None:
                outcome.messages.append(msg)
                step_discourse.append(msg)
            else:
                outcome.messages.append(
                    self._llm_skip(
                        obs=obs,
                        agent_id=agent_id,
                        phase=DeliberationPhase.DELIBERATION,
                        reason="parse_failed_or_empty_message",
                        decision_source="llm_parse_fail",
                    )
                )

        reps = self._action_rep_ids(obs.step)
        action_turns = run_parallel(
            [
                self._llm_action_turn(
                    obs,
                    situation,
                    step_discourse,
                    rep,
                    n_reps=len(reps),
                    slot=slot,
                )
                for slot, rep in enumerate(reps)
            ]
        )
        for action_msgs, action_cmds in action_turns:
            outcome.messages.extend(action_msgs)
            outcome.commands.extend(action_cmds)
        return outcome

    def _run_step_labeled(self, obs: EclssLoopObservation) -> StepEclssOutcome:
        outcome = StepEclssOutcome()
        reps = self._action_rep_ids(obs.step)
        if not reps:
            return outcome
        co2_high = float(self.policy.get("co2_storage_high_kg", DEFAULT_CO2_STORAGE_HIGH_KG))
        co2_critical = float(self.policy.get("co2_storage_critical_kg", DEFAULT_CO2_STORAGE_CRITICAL_KG))
        o2_low = float(self.policy.get("o2_storage_low_kg", DEFAULT_O2_STORAGE_LOW_KG))
        co2 = obs.telemetry.co2_storage_kg
        o2 = obs.telemetry.o2_storage_kg

        if co2 is not None and co2 >= co2_high and not self.state.alert_sent:
            self.state.alert_sent = True
            band = "critical" if co2 >= co2_critical else "high"
            outcome.messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role=reps[0],
                    to_role="team",
                    message=(
                        f"CO2 storage {co2:.1f} kg exceeds {band} band "
                        f"({co2_critical:.1f} kg critical / {co2_high:.1f} kg high)."
                    ),
                    message_type="alert",
                    reasoning="Storage telemetry threshold crossed.",
                    metadata=self._rule_metadata(),
                )
            )

        messages, commands = self._labeled_recovery(
            obs, reps, co2_high, co2_critical, o2_low, co2, o2
        )
        outcome.messages.extend(messages)
        outcome.commands.extend(commands)
        return outcome

    def _rearm_labeled_recovery(
        self,
        co2: Optional[float],
        o2: Optional[float],
        co2_high: float,
        o2_low: float,
    ) -> None:
        """Re-arm one-shot flags when telemetry returns to the safe band."""
        if co2 is not None and co2 < co2_high:
            self.state.ars_invoked = False
            self.state.ars_critical_escalated = False
            self.state.alert_sent = False
            self.state.co2_at_ars_dispatch = None
        elif (
            self.state.ars_invoked
            and co2 is not None
            and self.state.co2_at_ars_dispatch is not None
            and co2 >= self.state.co2_at_ars_dispatch
        ):
            # ARS had no effect — allow retry on the next step.
            self.state.ars_invoked = False
        if o2 is not None and o2 > o2_low:
            self.state.ogs_invoked = False
            self.state.co2_requested = False
            self.state.o2_at_ogs_dispatch = None
        elif (
            self.state.ogs_invoked
            and o2 is not None
            and self.state.o2_at_ogs_dispatch is not None
            and o2 <= self.state.o2_at_ogs_dispatch
        ):
            self.state.ogs_invoked = False

    def _waste_buffers(self, obs: EclssLoopObservation) -> Tuple[float, float]:
        grey_l = float(obs.telemetry.grey_water_collected_l or 0.0)
        urine_l = 0.0
        raw_topics = obs.telemetry.raw_topics or {}
        plant_sim_topics = raw_topics.get("plant_sim") if isinstance(raw_topics, dict) else {}
        if isinstance(plant_sim_topics, dict):
            urine_l = float(plant_sim_topics.get("urine_buffer_l") or 0.0)
            if plant_sim_topics.get("grey_water_l") is not None:
                grey_l = float(plant_sim_topics.get("grey_water_l") or 0.0)
        return urine_l, grey_l

    def _waste_feed_l(self, obs: EclssLoopObservation) -> float:
        urine_l, grey_l = self._waste_buffers(obs)
        return urine_l + grey_l

    def _backend_kind(self) -> Optional[str]:
        backend = self.config.get("backend")
        if isinstance(backend, dict):
            kind = backend.get("kind")
            if isinstance(kind, str) and kind.strip():
                return kind.strip()
        return None

    def _plant_config(self) -> Optional[PlantSimConfig]:
        if self._backend_kind() == "mock":
            return None
        plant_raw = self.config.get("plant_sim")
        if not isinstance(plant_raw, dict) or not plant_raw:
            return None
        try:
            return PlantSimConfig.from_scenario_config(
                {
                    "plant_sim": plant_raw,
                    "simulation": self.config.get("simulation") or {},
                    "thresholds": self.config.get("thresholds") or {},
                }
            )
        except PlantConfigError:
            return None

    def _ars_effect_kg(self, *, in_critical: bool) -> float:
        goal = float((self.policy.get("ars_goal") or {}).get("initial_co2_mass", 1.8))
        if in_critical:
            goal *= 1.5
        plant = self._plant_config()
        if plant is not None:
            capacity = per_interval(plant.ars_capacity_kg_day, plant.ars_operation_seconds)
            ref = max(float(plant.ars_reference_goal_co2_kg), 1e-9)
            return max(1e-9, capacity * (goal / ref))
        mock = self.config.get("mock_dynamics") or {}
        base = float(mock.get("ars_co2_reduction_kg", 0.35))
        ref = float(mock.get("ars_reference_co2_mass_kg", 1.8))
        return max(1e-9, base * (goal / ref if ref else 1.0))

    def _ogs_effect_kg(self) -> float:
        water_kg = float((self.policy.get("ogs_goal") or {}).get("input_water_mass", 0.015))
        from_water = water_kg / max(WATER_PER_O2, 1e-9)
        plant = self._plant_config()
        if plant is not None:
            cap = per_interval(plant.ogs_max_o2_kg_day, plant.ogs_operation_seconds)
            return max(1e-9, min(from_water, cap))
        return max(1e-9, from_water)

    def _wrs_max_feed_l(self) -> float:
        plant = self._plant_config()
        if plant is not None:
            return float(plant.wrs_max_feed_l_per_operation)
        return 10.0

    def _labeled_needed_counts(
        self,
        obs: EclssLoopObservation,
        *,
        co2_high: float,
        co2_critical: float,
        o2_low: float,
        co2: Optional[float],
        o2: Optional[float],
    ) -> Dict[str, int]:
        co2 = _finite_reading(co2)
        o2 = _finite_reading(o2)
        in_critical = co2 is not None and co2 >= co2_critical
        water_low = float(self.policy.get("product_water_low_l", DEFAULT_PRODUCT_WATER_LOW_L))
        water = _finite_reading(obs.telemetry.product_water_reserve_l)
        urine_l, grey_l = self._waste_buffers(obs)
        waste_feed_l = urine_l + grey_l
        wrs_trigger_l = float(self.policy.get("wrs_feed_trigger_l", 0.5))
        urine_req = float((self.policy.get("wrs_goal") or {}).get("urine_volume", 2.0))
        ars_n = 0
        if co2 is not None and co2 >= co2_high:
            ars_n = _ceil_positive((co2 - co2_high) + 1e-6, self._ars_effect_kg(in_critical=in_critical))
        ogs_n = 0
        if o2 is not None and o2 <= o2_low:
            ogs_n = _ceil_positive((o2_low - o2) + 1e-6, self._ogs_effect_kg())
        wrs_n = 0
        water_low_band = water is not None and water <= water_low
        if waste_feed_l >= wrs_trigger_l or (water_low_band and waste_feed_l > 0.0):
            wrs_n = _wrs_batches_to_empty(
                urine_l,
                grey_l,
                urine_request_l=urine_req,
                max_feed_l=self._wrs_max_feed_l(),
            )
            if wrs_n == 0 and waste_feed_l > 0.0:
                wrs_n = 1
        return {"ars": ars_n, "ogs": ogs_n, "wrs": wrs_n}

    def _labeled_recovery(
        self,
        obs: EclssLoopObservation,
        reps: List[str],
        co2_high: float,
        co2_critical: float,
        o2_low: float,
        co2: Optional[float],
        o2: Optional[float],
    ) -> Tuple[List[AgentMessage], List[EclssOperationalCommand]]:
        self._rearm_labeled_recovery(co2, o2, co2_high, o2_low)
        messages: List[AgentMessage] = []
        commands: List[EclssOperationalCommand] = []
        in_critical = co2 is not None and co2 >= co2_critical
        wrs_trigger_l = float(self.policy.get("wrs_feed_trigger_l", 0.5))
        waste_feed_l = self._waste_feed_l(obs)
        counts = self._labeled_needed_counts(
            obs,
            co2_high=co2_high,
            co2_critical=co2_critical,
            o2_low=o2_low,
            co2=co2,
            o2=o2,
        )
        slots = interleave_labeled_actions(counts, self.max_actions_per_step)
        for slot, name in enumerate(slots):
            extra_msgs, extra_cmds = self._emit_labeled_subsystem(
                obs,
                reps[slot % len(reps)],
                name,
                co2=co2,
                o2=o2,
                co2_high=co2_high,
                co2_critical=co2_critical,
                o2_low=o2_low,
                waste_feed_l=waste_feed_l,
                wrs_trigger_l=wrs_trigger_l,
                in_critical=in_critical,
            )
            messages.extend(extra_msgs)
            commands.extend(extra_cmds)
        return messages, commands

    def _emit_labeled_subsystem(
        self,
        obs: EclssLoopObservation,
        rep: str,
        name: str,
        *,
        co2: Optional[float],
        o2: Optional[float],
        co2_high: float,
        co2_critical: float,
        o2_low: float,
        waste_feed_l: float,
        wrs_trigger_l: float,
        in_critical: bool,
    ) -> Tuple[List[AgentMessage], List[EclssOperationalCommand]]:
        messages: List[AgentMessage] = []
        commands: List[EclssOperationalCommand] = []
        if name == "ars":
            ars_payload = dict(self.policy.get("ars_goal", {}))
            if in_critical:
                base_mass = float(ars_payload.get("initial_co2_mass", 1.8))
                ars_payload["initial_co2_mass"] = base_mass * 1.5
            commands.append(
                EclssOperationalCommand(
                    kind="air_revitalisation",
                    payload=ars_payload,
                    issued_by=rep,
                )
            )
            self.state.ars_invoked = True
            self.state.co2_at_ars_dispatch = co2
            if in_critical:
                self.state.ars_critical_escalated = True
            messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role=rep,
                    to_role="team",
                    message=(
                        "Starting escalated ARS air_revitalisation (critical band)."
                        if in_critical
                        else "Starting ARS air_revitalisation to vent CO2 from storage."
                    ),
                    message_type="operational_command",
                    reasoning=(
                        f"CO2 storage {co2:.1f} kg >= critical {co2_critical:.1f} kg; escalated ARS."
                        if in_critical
                        else f"CO2 storage {co2:.1f} kg >= {co2_high:.1f} kg."
                    ),
                    metadata=self._rule_metadata(),
                )
            )
            return messages, commands
        if name == "ogs":
            if self.policy.get("request_co2_before_ogs", False) and not self.state.co2_requested:
                amount = float(self.policy.get("request_co2_amount", 0.025))
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
            self.state.o2_at_ogs_dispatch = o2
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
        wrs_payload = dict(self.policy.get("wrs_goal", {"urine_volume": 2.0}))
        commands.append(
            EclssOperationalCommand(
                kind="water_recovery",
                payload=wrs_payload,
                issued_by=rep,
            )
        )
        feed_meets_trigger = waste_feed_l >= wrs_trigger_l
        messages.append(
            AgentMessage(
                step=obs.step,
                from_role=rep,
                to_role="team",
                message=(
                    "Starting WRS water_recovery to reclaim urine/grey water."
                    if feed_meets_trigger
                    else "Starting WRS water_recovery because product water is LOW (feed below trigger)."
                ),
                message_type="operational_command",
                reasoning=self._wrs_start_reasoning(
                    obs, waste_feed_l=waste_feed_l, wrs_trigger_l=wrs_trigger_l
                ),
                metadata=self._rule_metadata(),
            )
        )
        return messages, commands

    def _wrs_start_reasoning(
        self,
        obs: EclssLoopObservation,
        *,
        waste_feed_l: float,
        wrs_trigger_l: float,
    ) -> str:
        if waste_feed_l >= wrs_trigger_l:
            return f"Waste feed {waste_feed_l:.2f} L >= {wrs_trigger_l:.2f} L."
        water_low = float(self.policy.get("product_water_low_l", DEFAULT_PRODUCT_WATER_LOW_L))
        water = obs.telemetry.product_water_reserve_l
        water_s = f"{water:.2f} L" if water is not None else "unknown"
        return (
            f"Product water {water_s} <= {water_low:.2f} L "
            f"with waste feed {waste_feed_l:.2f} L (below trigger {wrs_trigger_l:.2f} L)."
        )

    async def _llm_deliberation_turn(
        self,
        *,
        obs: EclssLoopObservation,
        agent_id: str,
        to_role: str,
        message_type: str,
        phase: str,
        situation: str,
        step_discourse: List[AgentMessage],
        team_discourse: List[AgentMessage],
        contract: str,
        required: tuple[str, ...],
    ) -> Optional[AgentMessage]:
        agent = self.agents[agent_id]
        ctx = agent.build_context(
            step=obs.step,
            phase=phase,
            situation=situation,
            step_discourse=step_discourse,
            team_discourse=team_discourse,
        )
        parsed = await agent.deliberate_async(
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
        metadata: Dict[str, Any] = {
            "decision_source": "llm",
            "deliberation_phase": phase,
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

    async def _llm_action_turn(
        self,
        obs: EclssLoopObservation,
        situation: str,
        step_discourse: List[AgentMessage],
        rep: str,
        n_reps: int = 1,
        slot: int = 0,
    ) -> Tuple[List[AgentMessage], List[EclssOperationalCommand]]:
        contract = eclss_operational_action_contract()
        agent = self.agents[rep]
        ctx = agent.build_context(
            step=obs.step,
            phase=DeliberationPhase.ACTION,
            situation=situation,
            step_discourse=step_discourse,
            team_discourse=self.memory_store.discourse.recent(),
        )
        parsed = await agent.deliberate_async(
            ctx,
            contract,
            PersonaAgent.action_round_hint(n_reps=n_reps, slot=slot),
            ("commands",),
        )
        if parsed is None:
            return [
                self._llm_skip(
                    obs=obs,
                    agent_id=rep,
                    phase=DeliberationPhase.ACTION,
                    reason="parse_failed",
                    decision_source="llm_parse_fail",
                )
            ], []

        message = parsed.data.get("message", "Assessed current state.")
        reasoning = parsed.data.get("reasoning", "")
        commands: List[EclssOperationalCommand] = []
        parse_notes: List[str] = []
        raw_commands = parsed.data.get("commands", [])
        if not isinstance(raw_commands, list):
            raw_commands = []

        for item in raw_commands:
            cmd, note = self._parse_llm_operational_command(item, issued_by=rep)
            if note:
                parse_notes.append(note)
            if cmd is not None:
                commands.append(cmd)

        base_meta: Dict[str, Any] = {
            "decision_source": "llm",
            "deliberation_phase": DeliberationPhase.ACTION,
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
                    agent_id=rep,
                    phase=DeliberationPhase.ACTION,
                    reason="empty_commands",
                    decision_source="llm_no_action",
                    parse_status=parsed.status,
                    parse_error=parsed.error,
                )
            ], []

        llm_msg = AgentMessage(
            step=obs.step,
            from_role=rep,
            to_role="team",
            message=str(message),
            message_type="operational_command",
            reasoning=str(reasoning),
            metadata=base_meta,
        )
        return [llm_msg], commands

    def _parse_llm_operational_command(
        self,
        item: Any,
        *,
        issued_by: str,
    ) -> Tuple[Optional[EclssOperationalCommand], Optional[str]]:
        if not isinstance(item, dict):
            return None, "operational command is not an object"
        kind = str(item.get("kind", "")).strip()
        payload = item.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        if kind not in _ECLSS_OPERATIONAL_KINDS:
            return None, f"unsupported operational kind: {kind}"

        if kind == "air_revitalisation":
            normalized = self._normalize_numeric_fields(payload, _ARS_GOAL_FIELDS)
            if normalized is None:
                return None, "air_revitalisation payload needs numeric ARS goal fields"
            return EclssOperationalCommand(kind=kind, payload=normalized, issued_by=issued_by), None

        if kind == "oxygen_generation":
            normalized = self._normalize_numeric_fields(payload, _OGS_GOAL_FIELDS)
            if normalized is None:
                return None, "oxygen_generation payload needs numeric OGS goal fields"
            return EclssOperationalCommand(kind=kind, payload=normalized, issued_by=issued_by), None

        if kind == "water_recovery":
            normalized = self._normalize_numeric_fields(payload, _WRS_GOAL_FIELDS)
            if normalized is None:
                return None, "water_recovery payload needs numeric WRS goal fields"
            return EclssOperationalCommand(kind=kind, payload=normalized, issued_by=issued_by), None

        if kind in {"request_co2", "request_o2"}:
            try:
                amount = float(payload.get("amount"))
            except (TypeError, ValueError):
                return None, f"{kind} payload.amount must be numeric"
            if not math.isfinite(amount) or amount <= 0.0:
                return None, f"{kind} payload.amount must be finite and positive"
            return (
                EclssOperationalCommand(kind=kind, payload={"amount": amount}, issued_by=issued_by),
                None,
            )

        return None, f"unsupported operational kind: {kind}"

    @staticmethod
    def _normalize_numeric_fields(
        payload: Dict[str, Any],
        allowed: frozenset[str],
    ) -> Optional[Dict[str, float]]:
        if not payload:
            return None
        normalized: Dict[str, float] = {}
        for key, value in payload.items():
            if key not in allowed:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                return None
            # L7/D5: reject NaN/Inf/negative quantities from LLM payloads.
            if not math.isfinite(number) or number < 0.0:
                return None
            normalized[key] = number
        return normalized or None

    def _llm_skip(
        self,
        *,
        obs: EclssLoopObservation,
        agent_id: str,
        phase: str,
        reason: str,
        decision_source: str,
        **extra: Any,
    ) -> AgentMessage:
        metadata: Dict[str, Any] = {
            "decision_source": decision_source,
            "deliberation_phase": phase,
            "skip_reason": reason,
        }
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
    def _goal_from_payload(
        payload: Any,
        allowed: frozenset[str],
        goal_cls: type,
    ) -> Tuple[Any, Optional[str]]:
        if not isinstance(payload, Mapping):
            return None, "payload must be an object"
        extra = sorted(str(key) for key in payload if key not in allowed)
        if extra:
            return None, "unknown goal fields: " + ", ".join(extra)
        normalized: Dict[str, float] = {}
        for key, value in payload.items():
            try:
                number = float(value)
            except (TypeError, ValueError):
                return None, f"{key} must be numeric"
            if not math.isfinite(number) or number < 0.0:
                return None, f"{key} must be a finite non-negative number"
            normalized[key] = number
        return goal_cls(**normalized), None

    def _apply_command(
        self,
        backend: EclssBackend,
        cmd: EclssOperationalCommand,
    ) -> Optional[Dict[str, Any]]:
        kind = cmd.kind
        payload = cmd.payload
        if kind == "air_revitalisation":
            goal, error = self._goal_from_payload(payload, _ARS_GOAL_FIELDS, ArsGoal)
            if error:
                return {
                    "kind": "/eclss/events/operational_rejected",
                    "command": cmd.to_dict(),
                    "message": error,
                }
            result = backend.send_air_revitalisation_goal(goal)
        elif kind == "oxygen_generation":
            goal, error = self._goal_from_payload(payload, _OGS_GOAL_FIELDS, OgsGoal)
            if error:
                return {
                    "kind": "/eclss/events/operational_rejected",
                    "command": cmd.to_dict(),
                    "message": error,
                }
            result = backend.send_oxygen_generation_goal(goal)
        elif kind == "water_recovery":
            goal, error = self._goal_from_payload(payload, _WRS_GOAL_FIELDS, WrsGoal)
            if error:
                return {
                    "kind": "/eclss/events/operational_rejected",
                    "command": cmd.to_dict(),
                    "message": error,
                }
            result = backend.send_water_recovery_goal(goal)
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

        success = bool(getattr(result, "success", False))
        event_kind = (
            "/eclss/events/operational_applied"
            if success
            else "/eclss/events/operational_rejected"
        )
        return {
            "kind": event_kind,
            "command": cmd.to_dict(),
            "result": result.to_dict(),
            "message": getattr(result, "summary_message", None) or getattr(result, "message", ""),
        }

    @staticmethod
    def _rule_metadata() -> Dict[str, Any]:
        return {"decision_source": "rule"}

    @staticmethod
    def _build_llm_client(llm_cfg: Dict[str, Any]) -> LLMClient:
        return build_llm_client(llm_cfg)


_ECLSS_OPERATIONAL_LEVERS = """\
### Operational levers (facility reference)
- air_revitalisation: ARS action — payload fields initial_co2_mass (kg),
  initial_moisture_content (percent 0–100), initial_contaminants (percent 0–100).
- oxygen_generation: OGS action — payload fields input_water_mass (kg),
  iodine_concentration (mg/L).
- water_recovery: WRS action — payload field urine_volume (L) taken from the urine
  buffer; condensate / grey water fills the rest of the batch automatically.
- request_co2: Service call — payload {"amount": <kg>} optional Sabatier feedstock;
  default policy leaves this to OGS-internal /ars/request_co2 (use only when
  request_co2_before_ogs is explicitly enabled or discourse justifies it).
- request_o2: Service call — payload {"amount": <kg>} withdraw O2 from plant /o2_storage reserve.
Actions are asynchronous; issue only commands justified by Telemetry and team discourse.
One command per subsystem per step: duplicates in the same step are rejected, and a
subsystem stays busy for the duration of its operation (ARS runs 80 minutes)."""


def build_llm_situation(obs: EclssLoopObservation) -> str:
    t = obs.telemetry
    plant = t.raw_topics.get("plant_sim") if isinstance(t.raw_topics, dict) else None
    plant = plant if isinstance(plant, dict) else {}
    telemetry = (
        f"step={obs.step}, co2_storage_kg={t.co2_storage_kg}, o2_storage_kg={t.o2_storage_kg}, "
        f"product_water_reserve_l={t.product_water_reserve_l}, "
        f"grey_water_collected_l={t.grey_water_collected_l}, "
        f"urine_buffer_l={plant.get('urine_buffer_l')}, "
        f"captured_co2_kg={plant.get('captured_co2_kg')}, "
        f"ars_failure_enabled={t.ars_failure_enabled}, "
        f"ogs_failure_enabled={t.ogs_failure_enabled}, wrs_failure_enabled={t.wrs_failure_enabled}"
    )
    health = obs.health if isinstance(obs.health, dict) else {}
    world_state = (
        f"overall={health.get('overall', 'unknown')}, "
        f"co2_status={health.get('co2_status', 'unknown')}, "
        f"o2_status={health.get('o2_status', 'unknown')}, "
        f"water_status={health.get('water_status', 'unknown')}\n"
        "(Descriptive assessment from the facility monitoring layer — not a command.)"
    )
    return (
        "Scenario: ssos_eclss_loop. SSOS ECLSS storage and subsystem ops.\n\n"
        f"### Telemetry\n{telemetry}\n\n"
        f"### World state\n{world_state}\n\n"
        f"{_ECLSS_OPERATIONAL_LEVERS}"
    )


