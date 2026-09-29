"""One command per subsystem per step at the execution gate (design doc §7)."""

from __future__ import annotations

from typing import List

from core.agents.persona import eclss_operational_action_contract
from environment.ssos.eclss.plant_sim.backend import PlantSimEclssBackend
from environment.ssos.eclss.plant_sim.config import PlantSimConfig
from scenario.agents.eclss_loop_types import EclssOperationalCommand, StepEclssOutcome
from scenario.agents.ssos_eclss_loop_team import (
    DUPLICATE_COMMAND_REASON,
    SsosEclssLoopTeam,
    build_llm_situation,
)
from scenario.agents.eclss_loop_types import EclssLoopObservation
from environment.ssos.eclss.types import EclssTelemetrySnapshot
from scenario.ssos_eclss_loop.loop_mock_backend import LoopMockEclssBackend


def _team() -> SsosEclssLoopTeam:
    return SsosEclssLoopTeam(
        {
            "mode": "labeled_rule_base",
            "team": {"count": 2, "id_prefix": "op"},
            "policy": {"ars_goal": {"initial_co2_mass": 1.8}},
        }
    )


def _plant_backend() -> PlantSimEclssBackend:
    return PlantSimEclssBackend(
        PlantSimConfig(
            crew_size=4,
            initial_cabin_co2_kg=50.0,
            initial_o2_kg=5.0,
            initial_product_water_l=200.0,
            initial_urine_buffer_l=20.0,
            initial_grey_water_l=10.0,
        )
    )


def _cmd(kind: str, **payload) -> EclssOperationalCommand:
    return EclssOperationalCommand(kind=kind, payload=payload, issued_by="op_1")


def _kinds(events: List[dict], event_kind: str) -> List[str]:
    return [
        (event.get("command") or {}).get("kind")
        for event in events
        if event.get("kind", "").endswith(event_kind)
    ]


def test_second_ars_in_one_step_is_rejected_as_duplicate():
    team, backend = _team(), _plant_backend()
    outcome = StepEclssOutcome()
    outcome.commands = [
        _cmd("air_revitalisation", initial_co2_mass=1.8),
        _cmd("air_revitalisation", initial_co2_mass=1.8),
    ]
    events = team.apply_outcome(backend, outcome)
    assert _kinds(events, "operational_applied") == ["air_revitalisation"]
    rejected = [e for e in events if e["kind"].endswith("operational_rejected")]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == DUPLICATE_COMMAND_REASON


def test_one_action_per_subsystem_in_the_same_step_is_allowed():
    team, backend = _team(), _plant_backend()
    outcome = StepEclssOutcome()
    outcome.commands = [
        _cmd("air_revitalisation", initial_co2_mass=1.8),
        _cmd("oxygen_generation", input_water_mass=0.1),
        _cmd("water_recovery", urine_volume=1.0),
    ]
    events = team.apply_outcome(backend, outcome)
    assert _kinds(events, "operational_applied") == [
        "air_revitalisation",
        "oxygen_generation",
        "water_recovery",
    ]
    assert not [e for e in events if e["kind"].endswith("operational_rejected")]


def test_services_have_their_own_slot_but_do_not_repeat():
    team, backend = _team(), _plant_backend()
    backend.model.state.captured_co2_kg = 1.0
    outcome = StepEclssOutcome()
    outcome.commands = [
        _cmd("air_revitalisation", initial_co2_mass=1.8),
        _cmd("request_co2", amount=0.01),  # different group from the ARS action
        _cmd("request_co2", amount=0.01),  # duplicate service
    ]
    events = team.apply_outcome(backend, outcome)
    assert _kinds(events, "operational_applied") == ["air_revitalisation", "request_co2"]
    rejected = [e for e in events if e["kind"].endswith("operational_rejected")]
    assert [e["reason"] for e in rejected] == [DUPLICATE_COMMAND_REASON]


def test_busy_rejection_is_reported_through_the_team():
    team, backend = _team(), _plant_backend()
    first = StepEclssOutcome()
    first.commands = [_cmd("air_revitalisation", initial_co2_mass=1.8)]
    assert _kinds(team.apply_outcome(backend, first), "operational_applied") == [
        "air_revitalisation"
    ]

    backend.advance_step()
    second = StepEclssOutcome()
    second.commands = [_cmd("air_revitalisation", initial_co2_mass=1.8)]
    events = team.apply_outcome(backend, second)
    rejected = [e for e in events if e["kind"].endswith("operational_rejected")]
    assert len(rejected) == 1
    assert rejected[0]["result"]["details"]["reason"] == "subsystem_busy"
    assert rejected[0]["result"]["details"]["remaining_steps"] == 3


def test_gate_does_not_change_what_the_labeled_policy_emits():
    """The gate is execution-side: outcome.commands is untouched (trunk #59)."""
    team = SsosEclssLoopTeam(
        {
            "mode": "labeled_rule_base",
            "team": {"count": 2, "id_prefix": "op"},
            "max_actions_per_step": 4,
            "mock_dynamics": {"ars_co2_reduction_kg": 0.35, "ars_reference_co2_mass_kg": 1.8},
            "policy": {"ars_goal": {"initial_co2_mass": 1.8}, "co2_storage_high_kg": 1.5},
        }
    )
    snap = EclssTelemetrySnapshot(co2_storage_kg=2.6, o2_storage_kg=10.0)
    obs = EclssLoopObservation(step=0, telemetry=snap, health={"overall": "warning"})
    outcome = team.run_step(LoopMockEclssBackend({"simulation": {}, "mock_dynamics": {}}), obs)
    assert [cmd.kind for cmd in outcome.commands] == ["air_revitalisation"] * 4


def test_llm_crew_can_see_wrs_and_the_urine_buffer():
    contract = eclss_operational_action_contract()
    assert "water_recovery" in contract
    assert "urine_volume" in contract

    snap = EclssTelemetrySnapshot(
        co2_storage_kg=1.0,
        o2_storage_kg=5.0,
        product_water_reserve_l=60.0,
        raw_topics={"plant_sim": {"urine_buffer_l": 3.25, "captured_co2_kg": 0.4}},
    )
    situation = build_llm_situation(
        EclssLoopObservation(step=3, telemetry=snap, health={"overall": "warning"})
    )
    assert "water_recovery: WRS action" in situation
    assert "urine_buffer_l=3.25" in situation
    assert "One command per subsystem per step" in situation
