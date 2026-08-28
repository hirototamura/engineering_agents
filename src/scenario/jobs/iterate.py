"""Chain ssos_eclss_loop runs: apply last proposals, pass history to the designer."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from scenario.jobs.executor import execute_run
from scenario.jobs.progress import IterateReporter
from scenario.jobs.spec import RunResult, RunSpec
from scenario.ssos_eclss_loop.design_proposals import (
    load_design_proposals,
    proposal_covers_prior,
)

ITERATE_SCENARIO = "ssos_eclss_loop"
ALLOWED_ITERATE_BACKENDS = frozenset({"mock", "plant_sim"})
VERDICT_IMPROVED = "IMPROVED"
VERDICT_NOT_IMPROVED = "NOT_IMPROVED"
VERDICT_INCONCLUSIVE = "INCONCLUSIVE"
REPLAY_BASELINE = "baseline-replay"
REPLAY_FINAL = "final-replay"


def frozen_requirements_payload(summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "thresholds": summary.get("thresholds"),
        "inject_failures": summary.get("inject_failures"),
        "crew_initial": summary.get("crew_initial"),
        "steps": summary.get("steps"),
        "backend": summary.get("backend"),
    }


def frozen_requirements_hash(summary: Dict[str, Any]) -> str:
    payload = json.dumps(frozen_requirements_payload(summary), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def design_llm_provenance(overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    llm = ((overrides or {}).get("agents") or {}).get("design") or {}
    if not isinstance(llm, dict):
        llm = {}
    llm = llm.get("llm") or {}
    if not isinstance(llm, dict):
        return {}
    out: Dict[str, Any] = {}
    for key in ("provider", "model", "temperature"):
        if llm.get(key) is not None:
            out[key] = llm[key]
    return out


def chain_verdict(
    *,
    stopped_reason: Optional[str],
    paired_replay: bool,
    replay_ok: bool,
    baseline_remaining: Any,
    final_remaining: Any,
) -> str:
    if stopped_reason:
        return VERDICT_INCONCLUSIVE
    if not paired_replay or not replay_ok:
        return VERDICT_INCONCLUSIVE
    if baseline_remaining is None or final_remaining is None:
        return VERDICT_INCONCLUSIVE
    try:
        baseline_n = int(baseline_remaining)
        final_n = int(final_remaining)
    except (TypeError, ValueError):
        return VERDICT_INCONCLUSIVE
    if final_n > baseline_n:
        return VERDICT_IMPROVED
    return VERDICT_NOT_IMPROVED


def prepare_chain_dir(chain_dir: Path, *, recreate: bool = True) -> Path:
    chain_dir = Path(chain_dir)
    if recreate and chain_dir.exists():
        shutil.rmtree(chain_dir)
    chain_dir.mkdir(parents=True, exist_ok=True)
    return chain_dir


def _iter_dir(chain_dir: Path, index: int) -> Path:
    return chain_dir / f"{index:02d}"


def _sim_steps(spec: RunSpec) -> int:
    raw = ((spec.overrides or {}).get("simulation") or {}).get("steps")
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return 1


def _with_design_none(overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = copy.deepcopy(overrides or {})
    agents = dict(merged.get("agents") or {})
    design = dict(agents.get("design") or {})
    design["mode"] = "none"
    agents["design"] = design
    merged["agents"] = agents
    return merged


def _summary_row(
    *,
    label: Any,
    result: RunResult,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    summary = dict(result.summary or {})
    row: Dict[str, Any] = {
        "iteration": label,
        "run_dir": str(result.run_dir),
        "exit_code": result.exit_code,
        "crew_initial": summary.get("crew_initial"),
        "crew_remaining": summary.get("crew_remaining"),
        "crew_lost": summary.get("crew_lost"),
        "crew_lost_by_cause": summary.get("crew_lost_by_cause"),
        "design_proposal_count": summary.get("design_proposal_count", 0),
        "design_decision_source": summary.get("design_decision_source"),
        "design_mode": summary.get("design_mode"),
        "design_coverage_complete": summary.get("design_coverage_complete"),
        "apply_proposals_path": summary.get("apply_proposals_path"),
        "applied_proposals_path": summary.get("applied_proposals_path"),
        "requirement_change_count": summary.get("requirement_change_count", 0),
        "requirements_hash": frozen_requirements_hash(summary) if summary else None,
    }
    if extra:
        row.update(extra)
    return row


def run_design_iterate(
    *,
    iterations: int,
    chain_dir: Path,
    base_spec: RunSpec,
    recreate: bool = True,
    paired_replay: bool = True,
    reporter: Optional[IterateReporter] = None,
) -> Dict[str, Any]:
    """Run *iterations* ssos_eclss_loop sims, applying only the previous applied file.

    Run N is the verification of proposal N-1. The last run's newly emitted
    proposals are recorded but not simulated (no run N+1). Verdict comes from
    paired baseline/final replays, not the adaptive first vs last remaining.
    """
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    if base_spec.scenario != ITERATE_SCENARIO:
        raise ValueError(f"iterate supports {ITERATE_SCENARIO} only, got {base_spec.scenario!r}")

    chain_dir = prepare_chain_dir(chain_dir, recreate=recreate)
    reporter = reporter or IterateReporter()
    steps = _sim_steps(base_spec)
    accumulated_history: List[Dict[str, Any]] = []
    prior_changes: List[Dict[str, Any]] = []
    runs: List[Dict[str, Any]] = []
    stopped_reason: Optional[str] = None
    last_apply_path: Optional[Path] = None
    verified_apply_path: Optional[Path] = None
    requirement_hash: Optional[str] = None

    for index in range(1, iterations + 1):
        output_dir = _iter_dir(chain_dir, index)
        apply_this_run = last_apply_path
        spec = RunSpec(
            scenario=base_spec.scenario,
            overrides=base_spec.overrides,
            output_dir=output_dir,
            run_id=None,
            results_root=None,
            recreate_output=True,
            seed=base_spec.seed,
            apply_proposals_path=apply_this_run,
            design_history=list(accumulated_history),
            prior_changes=list(prior_changes),
            design_strict=True,
        )
        reporter.on_run_start(
            index=index,
            total=iterations,
            label=str(index),
            steps=steps,
            kind="iteration",
        )
        result: RunResult = execute_run(
            spec,
            on_step=lambda step, n: reporter.on_step(step=step, steps=n),
            on_phase=lambda detail: reporter.on_phase(detail),
        )
        row = _summary_row(
            label=index,
            result=result,
            extra={"final_verification": index == iterations},
        )
        runs.append(row)
        reporter.on_run_end(row)

        if result.exit_code != 0:
            stopped_reason = result.error or f"iteration {index} failed"
            break

        current_hash = row["requirements_hash"]
        if requirement_hash is None:
            requirement_hash = current_hash
        elif current_hash != requirement_hash:
            stopped_reason = (
                f"frozen requirements hash changed at iteration {index}: "
                f"{requirement_hash} -> {current_hash}"
            )
            break

        summary = dict(result.summary or {})
        proposals_path = (
            Path(summary["design_proposals_path"])
            if summary.get("design_proposals_path")
            else output_dir / "design_proposals.json"
        )
        # Empty / missing / incomplete proposals keep the last applied file
        # (or the initial YAML) so the configured iteration count still runs.
        if proposals_path.exists():
            proposals = load_design_proposals(proposals_path)
            new_changes = list(proposals.get("changes") or [])
            covers, _missing = proposal_covers_prior(new_changes, prior_changes)
            accumulated_history.append({"iteration": index, "changes": new_changes})
            applied_path = output_dir / "applied_proposals.json"
            if covers and applied_path.exists():
                prior_changes = list(load_design_proposals(applied_path).get("changes") or [])
                last_apply_path = applied_path
        else:
            accumulated_history.append({"iteration": index, "changes": []})
        if index == iterations:
            verified_apply_path = apply_this_run

    first_remaining = runs[0].get("crew_remaining") if runs else None
    last_remaining = runs[-1].get("crew_remaining") if runs else None
    completed = len([r for r in runs if r.get("exit_code") == 0])
    replay_ok = False
    baseline_remaining = None
    final_remaining = None
    replay_runs: List[Dict[str, Any]] = []

    chain_finished = stopped_reason is None and completed == iterations
    verdict_stop = stopped_reason
    if chain_finished and paired_replay:
        replay_overrides = _with_design_none(base_spec.overrides)
        replay_ok = True
        for label, apply_path in (
            (REPLAY_BASELINE, None),
            (REPLAY_FINAL, verified_apply_path),
        ):
            reporter.on_run_start(
                index=iterations,
                total=iterations,
                label=label,
                steps=steps,
                kind="replay",
            )
            replay_result = execute_run(
                RunSpec(
                    scenario=base_spec.scenario,
                    overrides=replay_overrides,
                    output_dir=chain_dir / label,
                    recreate_output=True,
                    seed=base_spec.seed,
                    apply_proposals_path=apply_path,
                    design_strict=True,
                ),
                on_step=lambda step, n: reporter.on_step(step=step, steps=n),
                on_phase=lambda detail: reporter.on_phase(detail),
            )
            replay_row = _summary_row(
                label=label,
                result=replay_result,
                extra={"paired_replay": True},
            )
            replay_runs.append(replay_row)
            reporter.on_run_end(replay_row)
            if replay_result.exit_code != 0:
                verdict_stop = replay_result.error or f"{label} failed"
                replay_ok = False
                break
            if requirement_hash is not None and replay_row.get("requirements_hash") != requirement_hash:
                verdict_stop = (
                    f"{label}: frozen requirements hash changed: "
                    f"{requirement_hash} -> {replay_row.get('requirements_hash')}"
                )
                replay_ok = False
                break
            if replay_row.get("design_mode") not in {None, "none"}:
                verdict_stop = (
                    f"{label}: expected design.mode none, got {replay_row.get('design_mode')}"
                )
                replay_ok = False
                break
        if replay_ok and len(replay_runs) == 2:
            baseline_remaining = replay_runs[0].get("crew_remaining")
            final_remaining = replay_runs[1].get("crew_remaining")
            verdict_stop = None
    elif not paired_replay:
        verdict_stop = stopped_reason or "paired replay disabled; no improvement claim"

    verdict = chain_verdict(
        stopped_reason=verdict_stop,
        paired_replay=paired_replay,
        replay_ok=replay_ok,
        baseline_remaining=baseline_remaining,
        final_remaining=final_remaining,
    )

    chain_summary = {
        "scenario": ITERATE_SCENARIO,
        "iterations_requested": iterations,
        "iterations_completed": completed,
        "claim": "controller-policy adaptation (action_profile / service_config)",
        "final_verification_iteration": completed,
        "unverified_proposals": bool(
            runs and (Path(str(runs[-1]["run_dir"])) / "design_proposals.json").exists()
        ),
        "crew_remaining_first": first_remaining,
        "crew_remaining_last": last_remaining,
        "crew_remaining_baseline_replay": baseline_remaining,
        "crew_remaining_final_replay": final_remaining,
        "paired_replay": paired_replay,
        "improved": verdict == VERDICT_IMPROVED,
        "verdict": verdict,
        "stopped_reason": verdict_stop,
        "requirements_hash": requirement_hash,
        "seed": base_spec.seed,
        "design_llm": design_llm_provenance(base_spec.overrides),
        "runs": runs,
        "replay_runs": replay_runs,
    }
    chain_summary["chain_dir"] = str(chain_dir)
    chain_summary["chain_summary_path"] = str(chain_dir / "chain_summary.json")
    (chain_dir / "chain_summary.json").write_text(
        json.dumps(chain_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (chain_dir / "summary.json").write_text(
        json.dumps(
            {
                "scenario": ITERATE_SCENARIO,
                "agents_mode": "iterate",
                "steps": (base_spec.overrides or {}).get("simulation", {}).get("steps"),
                "verdict": verdict,
                "crew_remaining_first": first_remaining,
                "crew_remaining_last": last_remaining,
                "crew_remaining_baseline_replay": baseline_remaining,
                "crew_remaining_final_replay": final_remaining,
                "iterations_completed": completed,
                "chain_summary_path": str(chain_dir / "chain_summary.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return chain_summary
