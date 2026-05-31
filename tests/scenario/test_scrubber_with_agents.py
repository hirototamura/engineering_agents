"""Regression tests for scrubber_degradation with labeled rule-based agents."""

from __future__ import annotations

import json
from pathlib import Path

from scenario.runner import run_scenario


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
    assert summary["provenance_record_count"] >= 1
    assert summary["provenance_path"].endswith("provenance.jsonl")

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
