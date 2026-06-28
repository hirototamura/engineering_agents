"""Host-side SSOS container run bridge (invoked from ea run)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

from scenario.jobs.resolve import default_results_root, resolve_run_id
from scenario.jobs.spec import RunResult, RunSpec
from scenario.runner import load_scenario_config
from tools.cli import exit_codes

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HOST_RUN_SCRIPT = _REPO_ROOT / "scripts" / "ssos_host_run.sh"
_CONTAINER_RESULTS_ROOT = Path("/ea/results")


def resolve_backend_kind(spec: RunSpec) -> str:
    overrides = spec.overrides or {}
    kind = (overrides.get("backend") or {}).get("kind")
    if kind:
        return str(kind)
    if spec.scenario == "ssos_eclss_loop":
        return "ros2"
    return "mock"


def should_run_ssos_in_container(spec: RunSpec) -> bool:
    if os.environ.get("EA_RUN_IN_CONTAINER"):
        return False
    if not shutil.which("docker"):
        return False
    return spec.scenario == "ssos_eclss_loop" and resolve_backend_kind(spec) == "ros2"


def run_ssos_in_container(spec: RunSpec) -> RunResult:
    if spec.output_dir is not None:
        return RunResult(
            run_dir=spec.output_dir,
            exit_code=exit_codes.USER_ERROR,
            error=(
                "--output-dir is not supported for ssos_eclss_loop ros2 runs. "
                "Use --run-id or --results-root with the mounted results directory."
            ),
        )

    if not _HOST_RUN_SCRIPT.is_file():
        return RunResult(
            run_dir=Path("."),
            exit_code=exit_codes.ENVIRONMENT_ERROR,
            error=f"Missing host runner script: {_HOST_RUN_SCRIPT}",
        )

    container_spec = _container_spec(spec)
    start = time.monotonic()
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as handle:
        job_path = Path(handle.name)
        handle.write(container_spec.to_json())

    try:
        proc = subprocess.run(
            ["bash", str(_HOST_RUN_SCRIPT), str(job_path)],
            cwd=_REPO_ROOT,
            check=False,
        )
    finally:
        job_path.unlink(missing_ok=True)

    duration_s = time.monotonic() - start
    host_run_dir = _host_run_directory(spec)
    if proc.returncode != 0:
        exit_code = exit_codes.USER_ERROR
        if proc.returncode == 3:
            exit_code = exit_codes.ENVIRONMENT_ERROR
        elif proc.returncode == 1:
            exit_code = exit_codes.RUN_FAILURE
        return RunResult(
            run_dir=host_run_dir,
            summary={},
            duration_s=duration_s,
            exit_code=exit_code,
            error=_failure_message(proc.returncode),
        )

    summary = _read_summary(host_run_dir)
    return RunResult(
        run_dir=host_run_dir,
        summary=summary,
        duration_s=duration_s,
        exit_code=exit_codes.SUCCESS,
    )


def _failure_message(returncode: int) -> str:
    if returncode == 3:
        return (
            "SSOS environment not ready (container stopped, volume mounts missing, "
            "or headless failed to start). See messages above and docs/cli.md."
        )
    if returncode == 2:
        return "SSOS host run rejected invalid input (see messages above)."
    return f"SSOS container run failed (exit {returncode})."


def _container_spec(spec: RunSpec) -> RunSpec:
    return RunSpec(
        scenario=spec.scenario,
        overrides=spec.overrides,
        output_dir=None,
        run_id=spec.run_id,
        results_root=_CONTAINER_RESULTS_ROOT,
        recreate_output=spec.recreate_output,
        seed=spec.seed,
        apply_proposals_path=spec.apply_proposals_path,
    )


def _host_run_directory(spec: RunSpec) -> Path:
    config = load_scenario_config(spec.scenario, spec.overrides)
    agents_config = config.get("agents")
    host_root = spec.results_root or default_results_root()
    run_id = resolve_run_id(
        spec.scenario,
        config.get("output", {}),
        agents_config,
        spec.run_id,
    )
    return host_root / run_id


def _read_summary(run_dir: Path) -> Dict[str, Any]:
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return {}
    return json.loads(summary_path.read_text(encoding="utf-8"))
