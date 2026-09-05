"""Execute a single simulation run from a RunSpec."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from scenario.jobs.spec import RunResult, RunSpec


def execute_run(
    spec: RunSpec,
    *,
    on_step: Optional[Callable[[int, int], None]] = None,
    on_phase: Optional[Callable[[str], None]] = None,
) -> RunResult:
    from scenario.runner import _scenario_registry

    start = time.monotonic()
    scenario = _scenario_registry().get(spec.scenario)
    if scenario is None:
        return RunResult(
            run_dir=Path("."),
            duration_s=time.monotonic() - start,
            exit_code=2,
            error=f"Unknown scenario: {spec.scenario!r}",
        )

    overrides = _apply_seed_override(spec.overrides, spec.seed)
    run_dir: Path | None = None

    try:
        if spec.scenario == "ssos_eclss_loop":
            from scenario.ssos_eclss_loop.scenario_run import SsosEclssLoopScenario

            run_dir = SsosEclssLoopScenario().run(
                output_dir=spec.output_dir,
                overrides=overrides,
                recreate_output=spec.recreate_output,
                apply_proposals_path=spec.apply_proposals_path,
                approve_provisional=spec.approve_provisional,
                run_id=spec.run_id,
                results_root=spec.results_root,
                design_history=spec.design_history,
                on_step=on_step,
                on_phase=on_phase,
                force=spec.force,
            )
        else:
            run_dir = scenario.run(
                output_dir=spec.output_dir,
                overrides=overrides,
                recreate_output=spec.recreate_output,
                run_id=spec.run_id,
                results_root=spec.results_root,
                force=spec.force,
            )
    except Exception as exc:
        return RunResult(
            run_dir=spec.output_dir or Path("."),
            duration_s=time.monotonic() - start,
            exit_code=1,
            error=str(exc),
        )
    finally:
        _teardown_rclpy_telemetry()

    duration_s = time.monotonic() - start
    summary = _read_summary(run_dir)
    summary["duration_wall_s"] = round(duration_s, 3)
    if spec.seed is not None:
        summary["seed"] = spec.seed
    _write_summary(run_dir, summary)

    exit_code = 0
    error = None
    if summary.get("evaluation_status") == "invalid":
        reasons = summary.get("evaluation_invalid_reasons") or []
        exit_code = 1
        error = "evaluation_status=invalid" + (
            ": " + ", ".join(str(item) for item in reasons) if reasons else ""
        )

    return RunResult(
        run_dir=run_dir,
        summary=summary,
        duration_s=duration_s,
        exit_code=exit_code,
        error=error,
    )


def _teardown_rclpy_telemetry() -> None:
    try:
        from environment.ssos.eclss.ros2.telemetry import reset_rclpy_telemetry_reader

        reset_rclpy_telemetry_reader()
    except Exception:
        pass


def _apply_seed_override(
    overrides: Dict[str, Any] | None,
    seed: int | None,
) -> Dict[str, Any] | None:
    if seed is None:
        return overrides
    merged: Dict[str, Any] = copy.deepcopy(overrides) if overrides else {}
    simulation = dict(merged.get("simulation") or {})
    simulation["seed"] = seed
    merged["simulation"] = simulation
    return merged


def _read_summary(run_dir: Path) -> Dict[str, Any]:
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return {}
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_summary(run_dir: Path, summary: Dict[str, Any]) -> None:
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
