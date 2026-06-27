"""CLI integration tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tools.cli.main import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_scenarios_lists_registered_scenarios():
    result = runner.invoke(app, ["scenarios"])
    assert result.exit_code == 0
    assert "scrubber_degradation" in result.stdout
    assert "ssos_eclss_loop" in result.stdout


def test_run_scrubber_short(tmp_path: Path):
    output_dir = tmp_path / "cli-run"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--output-dir",
            str(output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert str(output_dir) in result.stdout
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["steps"] == 2


def test_run_unknown_scenario():
    result = runner.invoke(app, ["run", "missing_scenario"])
    assert result.exit_code == 2
    assert "Unknown scenario" in result.stdout + result.stderr


def test_run_dry_run_write_spec(tmp_path: Path):
    spec_path = tmp_path / "job.json"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--dry-run",
            "--write-spec",
            str(spec_path),
        ],
    )
    assert result.exit_code == 0
    assert spec_path.exists()
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    assert payload["scenario"] == "scrubber_degradation"


def test_job_run_from_spec(tmp_path: Path):
    output_dir = tmp_path / "job-run"
    spec_path = tmp_path / "job.json"
    spec_path.write_text(
        json.dumps(
            {
                "scenario": "scrubber_degradation",
                "overrides": {"agents": {"mode": "none"}, "simulation": {"steps": 2}},
                "output_dir": str(output_dir),
                "recreate_output": True,
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["job", "run", str(spec_path), "--quiet"])
    assert result.exit_code == 0
    assert (output_dir / "summary.json").exists()
