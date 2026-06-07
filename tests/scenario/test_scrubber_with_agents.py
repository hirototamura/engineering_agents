"""Regression tests for scrubber_degradation with labeled rule-based agents."""

from __future__ import annotations

import json
from pathlib import Path

from environment.protocol import DesignChangeKind, HealthMetrics, HealthStatus, TelemetrySnapshot
from scenario.runner import run_scenario
from scenario.agents.scrubber_degradation_team import ScrubberDegradationTeam
from scenario.agents.types import AgentObservation


def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_scrubber_degradation_labeled_agents_recover(tmp_path: Path):
    run_dir = run_scenario(
        "scrubber_degradation",
        output_dir=tmp_path / "labeled",
        overrides={"agents": {"mode": "labeled"}},
        recreate_output=True,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    messages = _read_jsonl(run_dir / "messages.jsonl")
    telemetry = _read_jsonl(run_dir / "telemetry.jsonl")
    design_state = _read_jsonl(run_dir / "design_state.jsonl")
    provenance = _read_jsonl(run_dir / "provenance.jsonl")
    events = _read_jsonl(run_dir / "events.jsonl")
    eps_telemetry = _read_jsonl(run_dir / "eps_telemetry.jsonl")

    assert summary["agents_mode"] == "labeled"
    assert summary["message_count"] > 0
    assert len(messages) == summary["message_count"]

    roles = {m["from_role"] for m in messages}
    assert "monitor" in roles
    assert "diagnostician" in roles
    assert "operator" in roles
    assert "design_engineer" in roles

    message_types = {m["message_type"] for m in messages}
    assert "alert" in message_types
    assert "diagnosis" in message_types
    assert "recovery_command" in message_types
    assert "assessment" in message_types
    assert "design_change" not in message_types

    assert summary["design_change_count"] == 0
    design_proposals = json.loads((run_dir / "design_proposals.json").read_text(encoding="utf-8"))
    assert summary["design_proposal_count"] >= 1
    assert any(c.get("change_kind") == "add_edge" for c in design_proposals.get("changes", []))
    assert summary["peak_co2_ppm"] > 1000.0
    assert summary["final_co2_ppm"] < 1000.0, "agents should drive CO2 back to safe band"
    assert summary["co2_recovered_below_threshold_step"] is not None

    final_step = telemetry[-1]
    assert final_step["co2_ppm"] < 1000.0
    assert "eps_support_w" in final_step
    assert "eps_support_steps_remaining" in final_step
    assert summary["provenance_record_count"] >= 2
    assert summary["provenance_path"].endswith("provenance.jsonl")
    assert len(eps_telemetry) == summary["steps"]
    assert summary["eps_boost_applied_step"] is not None
    assert summary["min_power_margin_w"] is not None
    assert any(p.get("change_kind") == "request_eps_boost" for p in provenance)
    assert any(p.get("record_type") == "recovery" for p in provenance)
    assert any(r.get("bcdu_mode") == "discharging" for r in eps_telemetry)

    last_design_state = design_state[-1]
    edges = last_design_state["topology"]["edges"]
    assert not any(
        edge["kind"] == "bypass"
        and edge["source"] == "manifold"
        and edge["target"] == "scrubber"
        for edge in edges
    ), "runtime simulation should not apply design engineer topology changes"
    assert provenance, "provenance should include recovery records"
    assert not any(p.get("change_kind") == "add_edge" for p in provenance)
    assert any(
        e.get("kind") == "/eclss/events/recovery_applied"
        and (e.get("command") or {}).get("kind") == "request_eps_boost"
        for e in events
    ), "operator should request EPS boost when power is critical"


def test_scrubber_degradation_labeled_llm_post_run_design_proposals(
    tmp_path: Path, monkeypatch
):
    class FakeClient:
        def generate(self, prompt: str) -> str:
            lower = prompt.lower()
            if "agent_id: monitor" in lower and "phase: deliberation_initial" in lower:
                return json.dumps(
                    {
                        "message": "LLM monitor: CO2 trend requires attention.",
                        "reasoning": "co2 trajectory is rising",
                    }
                )
            if "agent_id: diagnostician" in lower and "phase: deliberation_initial" in lower:
                return json.dumps(
                    {
                        "message": "LLM diagnosis: scrubber degradation confirmed.",
                        "reasoning": "anomaly flags and efficiency drop align",
                    }
                )
            if "agent_id: operator" in lower and "phase: deliberation_initial" in lower:
                return json.dumps(
                    {
                        "message": "Assessing recovery options.",
                        "reasoning": "waiting for more data",
                    }
                )
            if "agent_id: design_engineer" in lower and "phase: deliberation_initial" in lower:
                return json.dumps(
                    {
                        "message": "LLM design: ops may not close the resilience gap.",
                        "reasoning": "structural bypass worth evaluating post-run",
                    }
                )
            if "agent_id: monitor" in lower and "phase: deliberation_react" in lower:
                return json.dumps(
                    {
                        "message": "Monitor reacts: trend still concerning.",
                        "reasoning": "no improvement in co2 slope",
                    }
                )
            if "agent_id: diagnostician" in lower and "phase: deliberation_react" in lower:
                return json.dumps(
                    {
                        "message": "Diagnostician reacts: degradation confirmed.",
                        "reasoning": "efficiency still falling",
                    }
                )
            if "agent_id: operator" in lower and "phase: action" in lower:
                return json.dumps(
                    {
                        "message": "LLM operator: defer to rule recovery timing.",
                        "reasoning": "test harness keeps anomaly narrative",
                        "commands": [],
                    }
                )
            if "agent_id: design_engineer" in lower and "phase: post_run_proposal" in lower:
                return json.dumps(
                    {
                        "message": "LLM design: increase scrubber base efficiency.",
                        "reasoning": "temporary operations indicate design margin gap",
                        "changes": [
                            {
                                "change_kind": "set_parameter",
                                "payload": {"key": "scrubber_base_efficiency", "value": 1.1},
                            }
                        ],
                    }
                )
            return "{}"

    monkeypatch.setattr(ScrubberDegradationTeam, "_build_llm_client", staticmethod(lambda _: FakeClient()))

    run_dir = run_scenario(
        "scrubber_degradation",
        output_dir=tmp_path / "labeled_llm",
        overrides={
            "agents": {"mode": "labeled_llm"},
        },
        recreate_output=True,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    messages = _read_jsonl(run_dir / "messages.jsonl")
    design_state = _read_jsonl(run_dir / "design_state.jsonl")
    provenance = _read_jsonl(run_dir / "provenance.jsonl")

    design_proposals = json.loads((run_dir / "design_proposals.json").read_text(encoding="utf-8"))

    assert summary["agents_mode"] == "labeled_llm"
    assert summary["design_change_count"] == 0
    assert summary["design_proposal_count"] >= 1
    assert any(m.get("decision_source") == "llm" for m in messages)
    assert any(m.get("deliberation_phase") == "deliberation_initial" for m in messages)
    assert any(m.get("deliberation_phase") == "action" for m in messages)
    assert not any(m.get("message_type") == "design_change" for m in messages)
    assert any(
        m.get("message_type") == "skip" and m.get("decision_source") == "llm_no_action"
        for m in messages
    ), "empty operator commands should be recorded as skip, not rule fallback"
    assert not any(m.get("decision_source") == "rule_fallback" for m in messages)
    assert design_proposals.get("decision_source") == "llm"
    assert any(c.get("change_kind") == "set_parameter" for c in design_proposals.get("changes", []))
    assert not any(p.get("change_kind") == "set_parameter" for p in provenance)

    final_parameters = design_state[-1]["parameters"]
    assert final_parameters["scrubber_base_efficiency"] < 1.1


def _obs(
    *,
    power_status: HealthStatus = HealthStatus.SAFE,
    eps_support_steps_remaining: int = 0,
) -> AgentObservation:
    return AgentObservation(
        step=1,
        telemetry=TelemetrySnapshot(
            step=1,
            co2_ppm=800.0,
            scrubber_efficiency=0.95,
            power_margin_w=50.0,
            fan_speed=0.7,
            bypass_enabled=False,
            load_reduced=False,
            anomaly_flags=[],
            eps_support_w=0.0,
            eps_support_steps_remaining=eps_support_steps_remaining,
        ),
        health=HealthMetrics(
            step=1,
            co2_status=HealthStatus.SAFE,
            power_status=power_status,
            overall=power_status,
        ),
    )


def test_llm_operator_parse_allows_repeated_commands_without_team_state():
    team = ScrubberDegradationTeam(
        {
            "mode": "labeled_llm",
            "roles": {"operator": {}},
            "llm": {},
        }
    )

    cmd1, note1 = team._parse_llm_operator_command({"kind": "set_fan_speed", "value": 0.8})
    cmd2, note2 = team._parse_llm_operator_command({"kind": "set_fan_speed", "value": 1.0})
    assert cmd1 is not None and note1 is None
    assert cmd2 is not None and note2 is None
    assert not team.state.fan_boost_applied

    cmd, note = team._parse_llm_operator_command({"kind": "enable_bypass", "value": "true"})
    assert cmd is not None
    assert note is None
    assert cmd.value is True

    cmd, note = team._parse_llm_operator_command({"kind": "enable_bypass", "value": "false"})
    assert cmd is not None
    assert note is None
    assert cmd.value is False

    cmd, note = team._parse_llm_operator_command({"kind": "request_eps_boost", "value": 120.0})
    assert cmd is not None
    assert note is None
    assert not team.state.eps_boost_requested


def test_llm_design_parse_supports_add_node_and_unrestricted_parameter():
    team = ScrubberDegradationTeam(
        {
            "mode": "labeled_llm",
            "roles": {"design_engineer": {}},
            "llm": {},
        }
    )

    node_change = team._parse_llm_design_change(
        "add_node",
        {"id": "aux_scrubber", "name": "Aux Scrubber", "kind": "scrubber"},
    )
    assert node_change is not None
    assert node_change.kind == DesignChangeKind.ADD_NODE

    param_change = team._parse_llm_design_change(
        "set_parameter",
        {"key": "custom_gain", "value": 0.42},
    )
    assert param_change is not None
    assert param_change.payload["key"] == "custom_gain"
