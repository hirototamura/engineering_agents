"""Unit tests for SsosEclssLoopTeam."""

from __future__ import annotations

from scenario.agents.eclss_loop_types import EclssLoopObservation
from scenario.agents.ssos_eclss_loop_team import SsosEclssLoopTeam
from scenario.ssos_eclss_loop.loop_mock_backend import LoopMockEclssBackend
from environment.ssos.eclss_types import EclssTelemetrySnapshot


def _team_config():
    return {
        "mode": "labeled_rule_base",
        "memory_limit": 4,
        "discourse_window": 4,
        "team": {"count": 2, "id_prefix": "op", "persona": "operator"},
        "policy": {
            "co2_storage_high_kg": 1500.0,
            "o2_storage_low_kg": 450.0,
            "request_co2_before_ogs": True,
            "request_co2_amount": 10.0,
            "ars_goal": {"initial_co2_mass": 900.0},
            "ogs_goal": {"input_water_mass": 5.0},
        },
    }


def test_team_applies_ars_to_backend():
    team = SsosEclssLoopTeam(_team_config())
    backend = LoopMockEclssBackend(
        {
            "simulation": {"initial_co2_storage_kg": 1700.0, "initial_o2_storage_kg": 500.0},
            "mock_dynamics": {},
        }
    )
    snap = backend.poll_telemetry()
    obs = EclssLoopObservation(step=0, telemetry=snap, health={"overall": "warning"})
    outcome = team.run_step(obs)
    assert len(outcome.commands) == 1
    assert outcome.commands[0].kind == "air_revitalisation"

    events = team.apply_outcome(backend, outcome)
    assert len(events) == 1
    assert events[0]["kind"] == "/eclss/events/operational_applied"
    assert backend.last_ars_goal is not None
    assert backend.poll_telemetry().co2_storage_kg < 1700.0


def test_team_no_design_change_commands():
    team = SsosEclssLoopTeam(_team_config())
    snap = EclssTelemetrySnapshot(co2_storage_kg=800.0, o2_storage_kg=600.0)
    obs = EclssLoopObservation(step=0, telemetry=snap, health={"overall": "safe"})
    outcome = team.run_step(obs)
    assert outcome.commands == []


def test_llm_operational_parse_air_revitalisation_and_request_co2():
    team = SsosEclssLoopTeam({"mode": "llm", "team": {"count": 1, "id_prefix": "op"}, "llm": {}})
    cmd, note = team._parse_llm_operational_command(
        {
            "kind": "air_revitalisation",
            "payload": {"initial_co2_mass": 1200.0, "initial_moisture_content": 20.0},
        },
        issued_by="op_1",
    )
    assert note is None
    assert cmd is not None
    assert cmd.kind == "air_revitalisation"
    assert cmd.payload["initial_co2_mass"] == 1200.0

    cmd2, note2 = team._parse_llm_operational_command(
        {"kind": "request_co2", "payload": {"amount": 15.0}},
        issued_by="op_1",
    )
    assert note2 is None
    assert cmd2 is not None
    assert cmd2.payload["amount"] == 15.0


def test_llm_design_parse_accepts_ssos_change_kinds():
    team = SsosEclssLoopTeam({"mode": "llm", "team": {"count": 1, "id_prefix": "op"}, "llm": {}})
    changes, notes = team._parse_llm_design_proposals(
        [
            {
                "change_kind": "action_profile",
                "payload": {
                    "subsystem": "ars",
                    "action": "air_revitalisation",
                    "fields": {"initial_co2_mass": 2000.0},
                },
            },
            {
                "change_kind": "set_parameter",
                "payload": {"target": "agents.policy.co2_storage_high_kg", "value": 1600.0},
            },
        ]
    )
    assert not notes
    assert len(changes) == 2
    assert changes[0]["change_kind"] == "action_profile"

