"""Regression tests for scrubber_degradation with labeled rule-based agents."""

from __future__ import annotations

import json
from pathlib import Path

from scenario.runner import run_scenario
from scenario.agents.scrubber_degradation_team import ScrubberDegradationTeam


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
    assert "design_change" in message_types

    assert summary["design_change_count"] >= 1
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
    assert any(
        edge["kind"] == "bypass"
        and edge["source"] == "manifold"
        and edge["target"] == "scrubber"
        for edge in edges
    ), "design_state should include a permanent bypass edge"
    assert provenance, "provenance should include at least one design change record"
    first_record = provenance[0]
    assert first_record["actor"] == "design_engineer"
    assert first_record["change_kind"] == "add_edge"
    assert first_record["trace"]["event_kind"] == "/eclss/events/design_change"
    assert any(
        e.get("kind") == "/eclss/events/recovery_applied"
        and (e.get("command") or {}).get("kind") == "request_eps_boost"
        for e in events
    ), "operator should request EPS boost when power is critical"


def test_scrubber_degradation_labeled_shadow_logs_llm_decisions(tmp_path: Path):
    run_dir = run_scenario(
        "scrubber_degradation",
        output_dir=tmp_path / "labeled_shadow",
        overrides={
            "simulation": {"steps": 5},
            "agents": {
                "mode": "labeled_shadow",
                "llm": {
                    "base_url": "http://127.0.0.1:11434",
                    "model": "llama3.2",
                    "api_timeout": 1,
                    "think": False,
                },
            },
        },
        recreate_output=True,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    messages = _read_jsonl(run_dir / "messages.jsonl")

    assert summary["agents_mode"] == "labeled_shadow"
    assert messages, "shadow mode should emit at least llm_shadow messages"
    assert any(m.get("decision_source") == "llm_shadow" for m in messages)
    assert any("parse_status" in m for m in messages if m.get("decision_source") == "llm_shadow")


def test_scrubber_degradation_labeled_llm_guarded_changes_provenance_and_parameters(
    tmp_path: Path, monkeypatch
):
    class FakeClient:
        def generate(self, prompt: str) -> str:
            lower = prompt.lower()
            if "role: monitor" in lower:
                return json.dumps(
                    {
                        "message": "LLM monitor: CO2 trend requires attention.",
                        "reasoning": "co2 trajectory is rising",
                    }
                )
            if "role: diagnostician" in lower:
                return json.dumps(
                    {
                        "message": "LLM diagnosis: scrubber degradation confirmed.",
                        "reasoning": "anomaly flags and efficiency drop align",
                    }
                )
            if "role: operator" in lower:
                # Empty commands → rule_fallback so CO2 can exceed 1000 before step 35
                # (aggressive LLM ops from step 1 prevent design_engineer thresholds).
                    return json.dumps(
                        {
                            "message": "LLM operator: defer to rule recovery timing.",
                            "reasoning": "test harness keeps anomaly narrative",
                            "commands": [],
                        }
                    )
            if "role: design_engineer" in lower:
                return json.dumps(
                    {
                        "apply_change": True,
                        "change_kind": "set_parameter",
                        "payload": {"key": "scrubber_base_efficiency", "value": 1.1},
                        "message": "LLM design: increase scrubber base efficiency.",
                        "reasoning": "temporary operations indicate design margin gap",
                    }
                )
            return "{}"

    monkeypatch.setattr(ScrubberDegradationTeam, "_build_llm_client", staticmethod(lambda _: FakeClient()))

    run_dir = run_scenario(
        "scrubber_degradation",
        output_dir=tmp_path / "labeled_llm_guarded",
        overrides={
            "agents": {"mode": "labeled_llm_guarded"},
        },
        recreate_output=True,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    messages = _read_jsonl(run_dir / "messages.jsonl")
    design_state = _read_jsonl(run_dir / "design_state.jsonl")
    provenance = _read_jsonl(run_dir / "provenance.jsonl")

    assert summary["agents_mode"] == "labeled_llm_guarded"
    assert summary["provenance_record_count"] >= 1
    assert any(m.get("decision_source") == "llm" for m in messages)
    assert any(p.get("change_kind") == "set_parameter" for p in provenance)
    assert any(
        p.get("trace", {}).get("decision_source") == "llm" for p in provenance
    ), "provenance trace should show llm-origin design decision"

    final_parameters = design_state[-1]["parameters"]
    assert final_parameters["scrubber_base_efficiency"] >= 1.1


def test_llm_guarded_operator_requires_literal_true_boolean():
    team = ScrubberDegradationTeam(
        {
            "mode": "labeled_llm_guarded",
            "roles": {"operator": {}},
            "llm": {},
        }
    )
    cmd, note = team._guard_operator_command({"kind": "enable_bypass", "value": "false"})
    assert cmd is None
    assert note == "bypass value must be literal true boolean"

    cmd, note = team._guard_operator_command({"kind": "reduce_load", "value": 1})
    assert cmd is None
    assert note == "reduce_load value must be literal true boolean"
