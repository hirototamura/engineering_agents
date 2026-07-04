"""Tests for ea doctor command."""

from __future__ import annotations

from unittest.mock import MagicMock

from typer.testing import CliRunner

from tools.cli.commands import doctor as doctor_cmd
from tools.cli.main import app

runner = CliRunner()


def test_python_support_status_ok():
    status, ok = doctor_cmd._python_support_status()
    assert ok is True
    assert status == "ok"


def test_python_support_status_rejects_old_python(monkeypatch):
    monkeypatch.setattr(doctor_cmd.sys, "version_info", (3, 9, 6))
    monkeypatch.setattr(doctor_cmd.sys, "version", "3.9.6 (test)", raising=False)
    status, ok = doctor_cmd._python_support_status()
    assert ok is False
    assert "requires 3.11+" in status
    assert "3.9.6" in status


def test_doctor_exits_with_environment_error_on_old_python(monkeypatch):
    monkeypatch.setattr(doctor_cmd.sys, "version_info", (3, 9, 6))
    monkeypatch.setattr(doctor_cmd.sys, "version", "3.9.6 (test)", raising=False)
    monkeypatch.setattr(doctor_cmd.shutil, "which", lambda _: None)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 3
    assert "unsupported" in result.output


def test_docker_status_not_installed(monkeypatch):
    monkeypatch.setattr(doctor_cmd.shutil, "which", lambda _: None)
    assert doctor_cmd._docker_status() == "not installed"


def test_docker_status_ok(monkeypatch):
    monkeypatch.setattr(doctor_cmd.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(
        doctor_cmd.subprocess,
        "run",
        lambda *args, **kwargs: MagicMock(returncode=0),
    )
    assert doctor_cmd._docker_status() == "ok"


def test_ssos_container_status_running(monkeypatch):
    monkeypatch.setattr(doctor_cmd.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setenv("SSOS_CONTAINER_NAME", "my-ssos")
    monkeypatch.setattr(
        doctor_cmd.subprocess,
        "run",
        lambda *args, **kwargs: MagicMock(returncode=0, stdout="my-ssos\nother\n"),
    )
    assert doctor_cmd._ssos_container_status() == "running (my-ssos)"


def test_ssos_mount_status_ok(monkeypatch):
    monkeypatch.setattr(doctor_cmd.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(
        doctor_cmd.subprocess,
        "run",
        lambda *args, **kwargs: MagicMock(returncode=0),
    )
    assert doctor_cmd._ssos_mount_status() == "ok"
