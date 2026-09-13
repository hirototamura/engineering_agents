"""Tests for RunSpec and run directory resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scenario.jobs.executor import execute_run
from scenario.jobs.resolve import resolve_run_directory, resolve_run_id
from scenario.jobs.spec import RunSpec
from scenario.scrubber_degradation.scenario_run import SCENARIO_REGISTRY


def test_write_json_creates_missing_parent(tmp_path: Path):
    path = tmp_path / "nested" / "dir" / "job.json"
    RunSpec(scenario="scrubber_degradation").write_json(path)
    assert path.is_file()
    assert RunSpec.read_json(path).scenario == "scrubber_degradation"


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


def test_resolve_run_id_ssos_mixed_modes_do_not_clobber_baseline():
    run_id = resolve_run_id(
        "ssos_eclss_loop",
        {
            "run_id": "ssos_eclss_loop_baseline",
            "run_id_labeled_rule_base": "ssos_eclss_loop_labeled_rule_base",
            "run_id_llm": "ssos_eclss_loop_llm",
        },
        {"actor": {"mode": "none"}, "design": {"mode": "llm"}},
    )
    assert run_id == "ssos_eclss_loop_none_llm"


def test_resolve_run_id_ssos_matching_modes_keep_legacy_ids():
    labeled = resolve_run_id(
        "ssos_eclss_loop",
        {"run_id": "baseline", "run_id_labeled_rule_base": "labeled"},
        {"actor": {"mode": "labeled_rule_base"}, "design": {}},
    )
    assert labeled == "labeled"


def test_resolve_run_id_rejects_path_traversal():
    with pytest.raises(ValueError, match="path separators"):
        resolve_run_id(
            "scrubber_degradation",
            {"run_id": "baseline"},
            None,
            run_id_override="../escape",
        )


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


def _stub_scrubber_run(monkeypatch, run_dir: Path) -> None:
    monkeypatch.setattr(
        SCENARIO_REGISTRY["scrubber_degradation"],
        "run",
        lambda **_kwargs: run_dir,
    )


def test_execute_run_fails_when_summary_is_missing(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _stub_scrubber_run(monkeypatch, run_dir)
    result = execute_run(RunSpec(scenario="scrubber_degradation", output_dir=run_dir))
    assert result.exit_code == 1
    assert "summary.json missing" in (result.error or "")
    assert not (run_dir / "summary.json").exists()


def test_execute_run_fails_when_summary_is_corrupt(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    broken = "{truncated"
    (run_dir / "summary.json").write_text(broken, encoding="utf-8")
    _stub_scrubber_run(monkeypatch, run_dir)
    result = execute_run(
        RunSpec(scenario="scrubber_degradation", output_dir=run_dir, seed=7)
    )
    assert result.exit_code == 1
    assert "not valid JSON" in (result.error or "")
    assert (run_dir / "summary.json").read_text(encoding="utf-8") == broken
    assert result.summary == {}


def test_execute_run_fails_when_summary_is_not_an_object(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text("[]\n", encoding="utf-8")
    _stub_scrubber_run(monkeypatch, run_dir)
    result = execute_run(RunSpec(scenario="scrubber_degradation", output_dir=run_dir))
    assert result.exit_code == 1
    assert "non-empty JSON object" in (result.error or "")
    assert (run_dir / "summary.json").read_text(encoding="utf-8") == "[]\n"


def test_execute_run_fails_when_summary_is_empty_object(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text("{}\n", encoding="utf-8")
    _stub_scrubber_run(monkeypatch, run_dir)
    result = execute_run(RunSpec(scenario="scrubber_degradation", output_dir=run_dir))
    assert result.exit_code == 1
    assert "non-empty JSON object" in (result.error or "")
    assert (run_dir / "summary.json").read_text(encoding="utf-8") == "{}\n"


def test_scenario_jobs_main_scrubber_short(tmp_path: Path, monkeypatch):
    spec_path = tmp_path / "job.json"
    RunSpec(
        scenario="scrubber_degradation",
        overrides={"agents": {"mode": "none"}, "simulation": {"steps": 1}},
        output_dir=tmp_path / "run",
        recreate_output=True,
    ).write_json(spec_path)

    from scenario.jobs import __main__ as jobs_main

    monkeypatch.setattr(jobs_main.sys, "argv", ["scenario.jobs", str(spec_path)])
    assert jobs_main.main() == 0
    assert (tmp_path / "run" / "summary.json").exists()


def test_scenario_jobs_main_missing_spec(tmp_path: Path, monkeypatch):
    from scenario.jobs import __main__ as jobs_main

    monkeypatch.setattr(jobs_main.sys, "argv", ["scenario.jobs", str(tmp_path / "nope.json")])
    assert jobs_main.main() == 2
