"""Tests for host Python resolution in SSOS Docker helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SSOS_DOCKER = REPO_ROOT / "scripts" / "lib" / "ssos_docker.sh"


def _resolve_host_python(*, env: dict[str, str] | None = None) -> str:
    script = (
        f"source {SSOS_DOCKER}; "
        "PATH=/usr/bin:/bin; "
        "unset -f python3 python 2>/dev/null || true; "
        "ssos_host_python"
    )
    result = subprocess.run(
        ["bash", "-lc", script],
        cwd=REPO_ROOT,
        env=env or os.environ.copy(),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_ssos_host_python_honors_python_env():
    env = {k: v for k, v in os.environ.items() if k != "PYTHON"}
    env["PYTHON"] = "/custom/python"
    assert _resolve_host_python(env=env) == "/custom/python"


def test_ssos_host_python_falls_back_to_available_interpreter():
    env = {k: v for k, v in os.environ.items() if k != "PYTHON"}
    env["PATH"] = "/usr/bin:/bin"
    resolved = _resolve_host_python(env=env)
    assert resolved in {"python3", "python", "/usr/bin/python3", "/usr/bin/python"}
