"""Tests for ssos_eclss_loop scenario (mock backend, no ROS2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scenario.runner import list_scenarios, run_scenario
from scenario.ssos_eclss_loop.scenario_run import (
    BACKEND_ENV_VAR,
    build_eclss_backend,
    resolve_backend_kind,
)
from scenario.ssos_eclss_loop.loop_mock_backend import LoopMockEclssBackend


def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_list_scenarios_includes_ssos_eclss_loop():
    assert "ssos_eclss_loop" in list_scenarios()


def test_ssos_eclss_loop_baseline_runs(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "baseline",
        recreate_output=True,
    )

    telemetry = _read_jsonl(run_dir / "telemetry.jsonl")
    health = _read_jsonl(run_dir / "health_metrics.jsonl")
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert summary["scenario"] == "ssos_eclss_loop"
    assert summary["backend"] == "mock"
    assert summary["agents_mode"] == "none"
    assert summary["steps"] == 8
    assert len(telemetry) == 8
    assert len(health) == 8
    assert summary["operational_command_count"] == 0
    assert summary["message_count"] == 0
    assert summary.get("ars_invoked_step") is None
    assert (run_dir / "provenance.jsonl").exists()
    assert (run_dir / "design_state.jsonl").exists() is False
    assert (run_dir / "design_proposals.json").exists() is False

    co2_series = [row["co2_storage_kg"] for row in telemetry]
    assert co2_series[0] == pytest.approx(1500.0)
    assert co2_series[-1] > co2_series[0], "CO2 should rise without agent intervention"


def test_ssos_eclss_loop_labeled_agents_invoke_ars(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "labeled",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        recreate_output=True,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    messages = _read_jsonl(run_dir / "messages.jsonl")
    events = _read_jsonl(run_dir / "events.jsonl")
    telemetry = _read_jsonl(run_dir / "telemetry.jsonl")

    assert summary["agents_mode"] == "labeled_rule_base"
    assert summary["team_count"] == 3
    assert summary["agent_ids"] == [
        "eclss_operator_1",
        "eclss_operator_2",
        "eclss_operator_3",
    ]
    assert summary["message_count"] > 0
    assert summary["operational_command_count"] >= 1
    assert summary["ars_invoked_step"] == 0

    message_types = {m["message_type"] for m in messages}
    assert "alert" in message_types
    assert "operational_command" in message_types
    assert "design_change" not in message_types

    applied = [e for e in events if e.get("kind") == "/eclss/events/operational_applied"]
    assert any(
        (e.get("command") or {}).get("kind") == "air_revitalisation" for e in applied
    )

    assert telemetry[0]["co2_storage_kg"] == pytest.approx(1500.0)
    assert telemetry[1]["co2_storage_kg"] < telemetry[0]["co2_storage_kg"], (
        "ARS should reduce CO2 storage after step 0"
    )
    assert (run_dir / "operational_proposals.json").exists()
    assert summary.get("operational_proposal_count", 0) >= 1


def test_ssos_eclss_loop_apply_proposals(tmp_path: Path):
    first = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "first",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        recreate_output=True,
    )
    proposals_path = first / "operational_proposals.json"
    assert proposals_path.exists()

    from scenario.ssos_eclss_loop.scenario_run import SsosEclssLoopScenario

    second = SsosEclssLoopScenario().run(
        output_dir=tmp_path / "second",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        apply_proposals_path=proposals_path,
    )
    summary = json.loads((second / "summary.json").read_text(encoding="utf-8"))
    assert summary["operational_command_count"] >= 1


def test_ssos_eclss_loop_labeled_agents_ogs_when_o2_low(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "ogs",
        overrides={
            "agents": {"mode": "labeled_rule_base"},
            "simulation": {"initial_o2_storage_kg": 420.0},
        },
        recreate_output=True,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    events = _read_jsonl(run_dir / "events.jsonl")

    assert summary["ogs_invoked_step"] == 0
    assert summary["co2_requested_step"] == 0
    applied_kinds = {
        (e.get("command") or {}).get("kind")
        for e in events
        if e.get("kind") == "/eclss/events/operational_applied"
    }
    assert "oxygen_generation" in applied_kinds
    assert "request_co2" in applied_kinds


def test_resolve_backend_kind_from_env(monkeypatch):
    config = {"backend": {"kind": "mock"}}
    monkeypatch.setenv(BACKEND_ENV_VAR, "ros2")
    assert resolve_backend_kind(config) == "ros2"


def test_resolve_backend_kind_override_wins(monkeypatch):
    config = {"backend": {"kind": "mock"}}
    monkeypatch.setenv(BACKEND_ENV_VAR, "ros2")
    assert resolve_backend_kind(config, overrides={"backend": {"kind": "mock"}}) == "mock"


def test_build_eclss_backend_mock():
    backend = build_eclss_backend({"simulation": {}, "mock_dynamics": {}}, kind="mock")
    assert isinstance(backend, LoopMockEclssBackend)


def test_build_eclss_backend_unknown_raises():
    with pytest.raises(ValueError, match="Unknown ECLSS backend"):
        build_eclss_backend({}, kind="invalid")
