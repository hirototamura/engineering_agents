"""Tests for SSOS host container bridge."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scenario.jobs.spec import RunSpec
from tools.cli.ssos_host import (
    resolve_backend_kind,
    run_ssos_in_container,
    should_run_ssos_in_container,
)


def test_resolve_backend_kind_defaults_ros2_for_ssos():
    spec = RunSpec(scenario="ssos_eclss_loop")
    assert resolve_backend_kind(spec) == "ros2"


def test_resolve_backend_kind_honors_override():
    spec = RunSpec(
        scenario="ssos_eclss_loop",
        overrides={"backend": {"kind": "mock"}},
    )
    assert resolve_backend_kind(spec) == "mock"


def test_should_run_ssos_in_container_requires_docker(monkeypatch):
    spec = RunSpec(scenario="ssos_eclss_loop")
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    assert should_run_ssos_in_container(spec) is False


def test_should_run_ssos_in_container_skips_inside_container(monkeypatch):
    spec = RunSpec(scenario="ssos_eclss_loop")
    monkeypatch.setenv("EA_RUN_IN_CONTAINER", "1")
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: "/usr/bin/docker")
    assert should_run_ssos_in_container(spec) is False


def test_should_run_ssos_in_container_mock_backend():
    spec = RunSpec(
        scenario="ssos_eclss_loop",
        overrides={"backend": {"kind": "mock"}},
    )
    assert should_run_ssos_in_container(spec) is False


def test_run_ssos_in_container_rejects_output_dir(tmp_path: Path):
    spec = RunSpec(
        scenario="ssos_eclss_loop",
        output_dir=tmp_path / "out",
    )
    result = run_ssos_in_container(spec)
    assert result.exit_code == 2
    assert "output-dir" in (result.error or "").lower()


def test_run_ssos_in_container_invokes_host_script(tmp_path: Path):
    summary_dir = tmp_path / "ssos_eclss_loop_labeled_rule_base"
    summary_dir.mkdir(parents=True)
    (summary_dir / "summary.json").write_text(
        json.dumps({"scenario": "ssos_eclss_loop", "duration_wall_s": 12.5}),
        encoding="utf-8",
    )
    spec = RunSpec(
        scenario="ssos_eclss_loop",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        results_root=tmp_path,
    )

    with patch("tools.cli.ssos_host.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("tools.cli.ssos_host._host_run_directory", return_value=summary_dir):
            result = run_ssos_in_container(spec)

    assert result.exit_code == 0
    assert result.summary.get("duration_wall_s") == 12.5
    mock_run.assert_called_once()
    assert "ssos_host_run.sh" in mock_run.call_args.args[0][1]


def test_run_ssos_in_container_failure_ignores_stale_summary(tmp_path: Path):
    summary_dir = tmp_path / "ssos_eclss_loop_labeled_rule_base"
    summary_dir.mkdir(parents=True)
    (summary_dir / "summary.json").write_text(
        json.dumps({"final_co2_storage_kg": 1570.0}),
        encoding="utf-8",
    )
    spec = RunSpec(
        scenario="ssos_eclss_loop",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        results_root=tmp_path,
    )

    with patch("tools.cli.ssos_host.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=3)
        with patch("tools.cli.ssos_host._host_run_directory", return_value=summary_dir):
            result = run_ssos_in_container(spec)

    assert result.exit_code == 3
    assert result.summary == {}
    assert "not ready" in (result.error or "").lower()
