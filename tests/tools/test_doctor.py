"""Tests for ea doctor command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.cli.commands import doctor as doctor_cmd


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
