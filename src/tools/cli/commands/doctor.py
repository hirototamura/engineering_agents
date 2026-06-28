"""Environment checks for CLI users."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

import typer

from core.llm.ollama import resolve_ollama_base_url
from scenario.jobs.resolve import RESULTS_ROOT_ENV_VAR, default_results_root
from tools.cli import exit_codes
from tools.cli.output import print_doctor_report
from tools.cli.ssos_host import _HOST_RESULTS_MOUNT, ssos_container_name


def register(app: typer.Typer) -> None:
    app.command("doctor")(doctor)


def _docker_status() -> str:
    if not shutil.which("docker"):
        return "not installed"
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        return f"daemon unreachable ({exc.__class__.__name__})"
    return "ok"


def _ssos_container_status() -> str:
    if not shutil.which("docker"):
        return "skipped (no docker)"
    container = ssos_container_name()
    try:
        proc = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        return f"check failed ({exc.__class__.__name__})"
    names = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if container in names:
        return f"running ({container})"
    return f"not running (expected: {container})"


def _ssos_mount_status() -> str:
    if not shutil.which("docker"):
        return "skipped (no docker)"
    container = ssos_container_name()
    try:
        subprocess.run(
            ["docker", "exec", container, "test", "-d", "/ea/src/scenario/ssos_eclss_loop"],
            check=True,
            capture_output=True,
            timeout=5,
        )
        subprocess.run(
            ["docker", "exec", container, "test", "-f", "/root/ssos-eclss-headless.sh"],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return f"missing or incomplete (container: {container})"
    return "ok"


def doctor() -> None:
    report = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "results_root": str(default_results_root()),
        "results_root_env": RESULTS_ROOT_ENV_VAR,
        "ssos_results_mount": str(_HOST_RESULTS_MOUNT),
        "docker": _docker_status(),
        "ssos_container": _ssos_container_status(),
        "ssos_mounts": _ssos_mount_status(),
    }

    try:
        import numpy  # noqa: F401
        import yaml  # noqa: F401

        report["dependencies"] = "ok"
    except ImportError as exc:
        report["dependencies"] = f"missing: {exc.name}"

    ollama_url = resolve_ollama_base_url()
    report["ollama_url"] = ollama_url
    try:
        import requests

        response = requests.get(f"{ollama_url}/api/tags", timeout=2)
        response.raise_for_status()
        report["ollama"] = "reachable"
    except Exception as exc:
        report["ollama"] = f"unreachable ({exc.__class__.__name__})"

    print_doctor_report(report)
    raise typer.Exit(exit_codes.SUCCESS)
