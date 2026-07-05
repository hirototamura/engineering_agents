"""SSOS container E2E regression hooks."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REGRESSION_SCRIPT = REPO_ROOT / "scripts" / "run_ssos_regression.sh"


def find_windows_bash() -> str | None:
    candidates = [
        os.environ.get("GIT_BASH"),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate

    bash = shutil.which("bash")
    if bash and "windows\\system32\\bash.exe" not in bash.lower():
        return bash
    return None


def regression_command(*args: str) -> list[str]:
    if os.name == "nt":
        bash = find_windows_bash()
        if bash is None:
            pytest.skip("Git Bash is required to run shell regression scripts on Windows")
        return [bash, str(REGRESSION_SCRIPT), *args]
    return [str(REGRESSION_SCRIPT), *args]


def test_regression_tier1_pytest_only():
    """Tier 1 path: run_ssos_regression.sh without SSOS_E2E always runs pytest."""
    env = {**os.environ}
    env.pop("SSOS_E2E", None)
    env.setdefault("PYTHON", sys.executable)
    result = subprocess.run(
        regression_command(),
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Tier 2 skipped" in result.stdout + result.stderr


@pytest.mark.ssos_e2e
def test_ssos_container_regression_tier2():
    """Tier 2: full smoke chain inside SSOS container (manual / self-hosted CI)."""
    if os.environ.get("SSOS_E2E") != "1":
        pytest.skip("set SSOS_E2E=1 to run live SSOS container regression")

    if not REGRESSION_SCRIPT.is_file():
        pytest.skip("regression script missing")

    cmd = regression_command("--skip-pytest")
    if os.environ.get("SSOS_E2E_WITH_EPS") == "1":
        cmd.append("--with-eps")
    if os.environ.get("SSOS_E2E_WITH_LLM") == "1":
        cmd.append("--with-llm")
    if os.environ.get("SSOS_USE_EXISTING") == "1":
        cmd.append("--use-existing")

    result = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    if result.returncode != 0:
        pytest.fail(f"SSOS regression failed with exit code {result.returncode}")
