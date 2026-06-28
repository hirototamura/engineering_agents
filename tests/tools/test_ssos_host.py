"""Tests for SSOS host container bridge."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scenario.jobs.spec import RunSpec
from tools.cli.ssos_host import (
    _HOST_RESULTS_MOUNT,
    check_ssos_ros2_host_environment,
    resolve_backend_kind,
    run_ssos_in_container,
    should_run_ssos_in_container,
    ssos_container_name,
)


def test_ssos_container_name_honors_env_precedence(monkeypatch):
    monkeypatch.setenv("SSOS_CONTAINER", "from-container")
    monkeypatch.setenv("SSOS_CONTAINER_NAME", "from-name")
    assert ssos_container_name() == "from-container"

    monkeypatch.delenv("SSOS_CONTAINER", raising=False)
    assert ssos_container_name() == "from-name"


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


def test_check_ssos_ros2_host_environment_blocks_without_docker(monkeypatch):
    spec = RunSpec(scenario="ssos_eclss_loop")
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    result = check_ssos_ros2_host_environment(spec)
    assert result is not None
    assert result.exit_code == 3
    assert "Docker is required" in (result.error or "")


def test_check_ssos_ros2_host_environment_allows_mock_backend(monkeypatch):
    spec = RunSpec(
        scenario="ssos_eclss_loop",
        overrides={"backend": {"kind": "mock"}},
    )
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    assert check_ssos_ros2_host_environment(spec) is None


def test_check_ssos_ros2_host_environment_allows_inside_container(monkeypatch):
    spec = RunSpec(scenario="ssos_eclss_loop")
    monkeypatch.setenv("EA_RUN_IN_CONTAINER", "1")
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    assert check_ssos_ros2_host_environment(spec) is None


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


def test_run_ssos_in_container_rejects_custom_results_root(tmp_path: Path):
    spec = RunSpec(
        scenario="ssos_eclss_loop",
        results_root=tmp_path / "custom",
    )
    result = run_ssos_in_container(spec)
    assert result.exit_code == 2
    assert "results-root" in (result.error or "").lower()


def test_run_ssos_in_container_rejects_missing_apply_proposals(tmp_path: Path):
    spec = RunSpec(
        scenario="ssos_eclss_loop",
        apply_proposals_path=tmp_path / "missing.json",
    )
    result = run_ssos_in_container(spec)
    assert result.exit_code == 2
    assert "not found" in (result.error or "").lower()


def test_run_ssos_in_container_copies_apply_proposals(tmp_path: Path):
    proposals = tmp_path / "design_proposals.json"
    proposals.write_text('{"changes": []}', encoding="utf-8")
    summary_dir = _HOST_RESULTS_MOUNT / "ssos_eclss_loop_labeled_rule_base"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "summary.json").write_text("{}", encoding="utf-8")
    spec = RunSpec(
        scenario="ssos_eclss_loop",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        apply_proposals_path=proposals,
    )

    with patch("tools.cli.ssos_host.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker cp
            MagicMock(returncode=0),  # host script
            MagicMock(returncode=0),  # docker exec rm
        ]
        with patch("tools.cli.ssos_host._host_run_directory", return_value=summary_dir):
            with patch("tools.cli.ssos_host._read_summary", return_value={"scenario": "ssos_eclss_loop"}):
                result = run_ssos_in_container(spec)

    assert result.exit_code == 0
    docker_cp = mock_run.call_args_list[0].args[0]
    assert docker_cp[:2] == ["docker", "cp"]
    assert str(proposals) in docker_cp[2]
    job_call = mock_run.call_args_list[1].args[0]
    assert "ssos_host_run.sh" in job_call[1]


def test_run_ssos_in_container_missing_summary_is_failure(tmp_path: Path):
    summary_dir = tmp_path / "ssos_eclss_loop_labeled_rule_base"
    summary_dir.mkdir(parents=True)
    spec = RunSpec(
        scenario="ssos_eclss_loop",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        results_root=_HOST_RESULTS_MOUNT,
    )

    with patch("tools.cli.ssos_host.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("tools.cli.ssos_host._host_run_directory", return_value=summary_dir):
            result = run_ssos_in_container(spec)

    assert result.exit_code == 1
    assert "summary.json is missing" in (result.error or "")


def test_run_ssos_in_container_invokes_host_script(tmp_path: Path):
    summary_dir = _HOST_RESULTS_MOUNT / "ssos_eclss_loop_labeled_rule_base"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "summary.json").write_text(
        json.dumps({"scenario": "ssos_eclss_loop", "duration_wall_s": 12.5}),
        encoding="utf-8",
    )
    spec = RunSpec(
        scenario="ssos_eclss_loop",
        overrides={"agents": {"mode": "labeled_rule_base"}},
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
    summary_dir = _HOST_RESULTS_MOUNT / "ssos_eclss_loop_labeled_rule_base"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "summary.json").write_text(
        json.dumps({"final_co2_storage_kg": 1570.0}),
        encoding="utf-8",
    )
    spec = RunSpec(
        scenario="ssos_eclss_loop",
        overrides={"agents": {"mode": "labeled_rule_base"}},
    )

    with patch("tools.cli.ssos_host.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=3)
        with patch("tools.cli.ssos_host._host_run_directory", return_value=summary_dir):
            result = run_ssos_in_container(spec)

    assert result.exit_code == 3
    assert result.summary == {}
    assert "not ready" in (result.error or "").lower()
