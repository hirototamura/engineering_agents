"""Tests for RunSpec and run directory resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scenario.jobs.resolve import resolve_run_id, resolve_run_directory
from scenario.jobs.spec import RunSpec
from scenario.jobs.executor import execute_run


def test_run_spec_json_roundtrip(tmp_path: Path):
    spec = RunSpec(
        scenario="scrubber_degradation",
        overrides={"simulation": {"steps": 3}},
        run_id="custom_run",
        seed=42,
    )
    path = tmp_path / "job.json"
    spec.write_json(path)
    loaded = RunSpec.read_json(path)
    assert loaded.scenario == spec.scenario
    assert loaded.overrides == spec.overrides
    assert loaded.run_id == spec.run_id
    assert loaded.seed == spec.seed


def test_resolve_run_id_prefers_explicit_override():
    run_id = resolve_run_id(
        "scrubber_degradation",
        {"run_id": "baseline", "run_id_labeled_rule_base": "labeled"},
        {"mode": "labeled_rule_base"},
        run_id_override="batch-001",
    )
    assert run_id == "batch-001"


def test_resolve_run_id_uses_agents_mode_mapping():
    run_id = resolve_run_id(
        "scrubber_degradation",
        {"run_id": "baseline", "run_id_llm": "llm_run"},
        {"mode": "llm"},
    )
    assert run_id == "llm_run"


def test_resolve_run_directory_with_explicit_output_dir(tmp_path: Path):
    run_dir = resolve_run_directory(
        scenario_name="scrubber_degradation",
        output_cfg={},
        agents_config=None,
        output_dir=tmp_path / "explicit",
        recreate_output=True,
    )
    assert run_dir == tmp_path / "explicit"
    assert run_dir.exists()


def test_execute_run_scrubber_short(tmp_path: Path):
    result = execute_run(
        RunSpec(
            scenario="scrubber_degradation",
            overrides={"agents": {"mode": "none"}, "simulation": {"steps": 2}},
            output_dir=tmp_path / "run",
            recreate_output=True,
        )
    )
    assert result.exit_code == 0
    assert (result.run_dir / "summary.json").exists()
    summary = json.loads((result.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["steps"] == 2
    assert summary["agents_mode"] == "none"


def test_execute_run_unknown_scenario():
    result = execute_run(RunSpec(scenario="does_not_exist"))
    assert result.exit_code == 2
    assert "Unknown scenario" in (result.error or "")
