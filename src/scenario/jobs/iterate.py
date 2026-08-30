"""Chain ssos_eclss_loop runs: apply last design_proposals, record history."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

from scenario.jobs.executor import execute_run
from scenario.jobs.progress import IterateReporter
from scenario.jobs.spec import RunResult, RunSpec
from scenario.ssos_eclss_loop.chain_memory import (
    capacity_keys_in_document,
    record_measured_limits,
    update_compact_chain_memory,
)
from scenario.ssos_eclss_loop.chain_selection import (
    select_chain_final_answer,
    write_chain_final_answer,
)
from scenario.ssos_eclss_loop.design_constraints import DesignConstraints
from scenario.ssos_eclss_loop.design_proposals import (
    complete_capacity_profile,
    load_design_proposals,
    supervisor_approval_reasons,
    write_design_proposals,
)
from scenario.ssos_eclss_loop.design_variables import read_capacity_fields
from scenario.ssos_eclss_loop.floor_probe import (
    measure_survival_limits,
    scenario_runner,
    write_measured_limits,
)

ITERATE_SCENARIO = "ssos_eclss_loop"
ALLOWED_ITERATE_BACKENDS = frozenset({"mock", "plant_sim"})
VERDICT_IMPROVED = "IMPROVED"
VERDICT_NOT_IMPROVED = "NOT_IMPROVED"
VERDICT_INCONCLUSIVE = "INCONCLUSIVE"
REPLAY_BASELINE = "baseline-replay"
REPLAY_FINAL = "final-replay"

ITERATION_COUNT_MIN = 1
ITERATION_COUNT_MAX = 50
DEFAULT_ITERATION_RUN_ID = "ssos_eclss_loop_design_iter"


@dataclass(frozen=True)
class IterationSettings:
    """Resolved chain job from scenario.yaml ``iteration:`` plus CLI overrides."""

    chain: bool
    count: int
    paired_replay: bool
    approve_provisional: bool
    run_id: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "chain": self.chain,
            "count": self.count,
            "paired_replay": self.paired_replay,
            "approve_provisional": self.approve_provisional,
            "run_id": self.run_id,
        }


def resolve_iteration(
    config: Optional[Mapping[str, Any]],
    *,
    cli_iterate: Optional[int] = None,
    cli_paired_replay: Optional[bool] = None,
    cli_approve_provisional: Optional[bool] = None,
    cli_run_id: Optional[str] = None,
) -> IterationSettings:
    """Merge ``iteration:`` from scenario config with explicit CLI flags.

    Child sims inherit the same scenario-level keys as a single run
    (``inject_failures``, ``backend``, actor/design modes). ``iteration.defaults``
    is rejected so a leftover block cannot silently diverge from those keys.
    """
    raw = dict((config or {}).get("iteration") or {})
    if "defaults" in raw:
        raise ValueError(
            "iteration.defaults was removed; chained runs use the same "
            "inject_failures, backend, and actor/design modes as a single run. "
            "Set those keys at scenario level, or pass --inject-failures / "
            "--backend / --actor-mode / --design-mode."
        )

    yaml_enabled = bool(raw.get("enabled", False))
    try:
        yaml_count = int(raw["count"]) if raw.get("count") is not None else 5
    except (TypeError, ValueError) as exc:
        raise ValueError("iteration.count must be an integer") from exc

    if cli_iterate is not None:
        chain = True
        count = int(cli_iterate)
    else:
        chain = yaml_enabled
        count = yaml_count

    if chain and not (ITERATION_COUNT_MIN <= count <= ITERATION_COUNT_MAX):
        raise ValueError(
            f"iteration count must be {ITERATION_COUNT_MIN}–{ITERATION_COUNT_MAX}, got {count}"
        )

    paired = bool(raw.get("paired_replay", True))
    if cli_paired_replay is not None:
        paired = bool(cli_paired_replay)

    approve = bool(raw.get("approve_provisional", True))
    if cli_approve_provisional is not None:
        approve = bool(cli_approve_provisional)

    run_id = str(cli_run_id or raw.get("run_id") or DEFAULT_ITERATION_RUN_ID)
    return IterationSettings(
        chain=chain,
        count=count,
        paired_replay=paired,
        approve_provisional=approve,
        run_id=run_id,
    )


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


def _canonical_payload(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


def _change_merge_key(change: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
    kind = change.get("change_kind")
    raw_payload = change.get("payload")
    payload = raw_payload if isinstance(raw_payload, Mapping) else {}
    if kind == "capacity_profile":
        return ("capacity_profile", str(payload.get("backend") or "plant_sim").lower())
    if kind == "action_profile":
        return ("action_profile", str(payload.get("subsystem") or "").lower())
    if kind == "service_config":
        return ("service_config", str(payload.get("service") or "").lower())
    if kind == "graph_rewire":
        return ("graph_rewire", _canonical_payload(payload))
    if kind == "set_parameter":
        return None
    return ("other", _canonical_payload({"kind": kind, "payload": payload}))


def _overlay_mapped_change(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    kind = incoming.get("change_kind")
    out = copy.deepcopy(incoming)
    old_payload = existing.get("payload") if isinstance(existing.get("payload"), dict) else {}
    new_payload = out.get("payload") if isinstance(out.get("payload"), dict) else {}
    if kind in {"action_profile", "capacity_profile"}:
        old_fields = old_payload.get("fields") if isinstance(old_payload.get("fields"), dict) else {}
        new_fields = new_payload.get("fields") if isinstance(new_payload.get("fields"), dict) else {}
        merged_payload = dict(new_payload)
        merged_payload["fields"] = {**old_fields, **new_fields}
        out["payload"] = merged_payload
    elif kind == "service_config":
        out["payload"] = {**old_payload, **new_payload}
    return out


def accumulate_applied_document(
    previous: Optional[Mapping[str, Any]],
    new: Mapping[str, Any],
) -> Dict[str, Any]:
    """Union earlier adopted changes with this round's document.

    Each child sim starts from the original YAML and applies one file.
    Replacing that file with a partial delta would revert ``action_profile``,
    ``service_config``, ``graph_rewire``, and any capacity keys the new
    document does not mention.
    """
    merged = copy.deepcopy(dict(new))
    incoming = [change for change in (new.get("changes") or []) if isinstance(change, dict)]
    if not previous:
        merged["changes"] = [
            copy.deepcopy(change)
            for change in incoming
            if change.get("change_kind") != "set_parameter"
        ]
        return merged

    ordered_keys: List[Tuple[str, str]] = []
    by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def ingest(change: Mapping[str, Any], *, overlay: bool) -> None:
        if not isinstance(change, dict) or change.get("change_kind") == "set_parameter":
            return
        key = _change_merge_key(change)
        if key is None:
            return
        if key in by_key:
            if overlay:
                by_key[key] = _overlay_mapped_change(by_key[key], change)
            return
        by_key[key] = copy.deepcopy(dict(change))
        ordered_keys.append(key)

    for change in previous.get("changes") or []:
        if isinstance(change, Mapping):
            ingest(change, overlay=False)
    for change in incoming:
        ingest(change, overlay=True)

    merged["changes"] = [by_key[key] for key in ordered_keys]
    return merged


def iterate_apply_document(
    proposals: Dict[str, Any],
    *,
    approve_provisional: bool = False,
    installed: Optional[Mapping[str, Any]] = None,
    previous: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Document the next iterate sim should apply.

    Unified generation (capacity_profile, action_profile, …) is kept. ``set_parameter``
    is dropped so verification thresholds stay frozen across the chain. Documents
    that still need supervisor approval are skipped unless *approve_provisional*.

    A capacity_profile that names only some keys is completed from *installed*
    (the machine this run actually flew). Omit means keep that value, not
    revert to the YAML baseline on the next apply.

    *previous* is the last adopted file. A later partial document is folded
    into it so earlier ARS/OGS/``graph_rewire`` work is not dropped when the
    designer names only a subset of fields.
    """
    kept: List[Dict[str, Any]] = []
    for change in proposals.get("changes") or []:
        if not isinstance(change, dict):
            continue
        if change.get("change_kind") == "set_parameter":
            continue
        kept.append(change)
    if not kept:
        return None
    document = copy.deepcopy(proposals)
    document["changes"] = kept
    document = accumulate_applied_document(previous, document)
    if installed:
        document = complete_capacity_profile(document, installed)
    if not approve_provisional and supervisor_approval_reasons(document):
        return None
    return document


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


def _installed_capacity(run_dir: Any) -> Dict[str, float]:
    """The machine this run actually flew, read back from its own config.

    The proposal says what was asked for; only the config says what was built,
    and a progress line that shows the score without the sizing beside it
    cannot be read.
    """
    config = _run_config(Path(str(run_dir)))
    return read_capacity_fields(config) if config else {}


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
        "evaluation_score": summary.get("evaluation_score"),
        "evaluation_max_score": summary.get("evaluation_max_score"),
        "evaluation_status": summary.get("evaluation_status"),
        "physics_gate_passed": summary.get("physics_gate_passed"),
        "installed_capacity": _installed_capacity(result.run_dir),
        "design_proposal_count": summary.get("design_proposal_count", 0),
        "design_decision_source": summary.get("design_decision_source"),
        "design_mode": summary.get("design_mode"),
        "final_status": summary.get("final_status") or summary.get("design_final_status"),
        "apply_proposals_path": summary.get("apply_proposals_path"),
        "applied_proposals_path": summary.get("applied_proposals_path"),
        "requirements_hash": frozen_requirements_hash(summary) if summary else None,
    }
    if extra:
        row.update(extra)
    return row


def _measure_survival_limits(
    chain_dir: Path,
    first_run_dir: Path,
    *,
    steps: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Find out where each subsystem stops keeping the crew alive, by trying it.

    Run once, before any design decision, from the machine the scenario ships
    with. Deterministic and cheap -- a 72-step simulation costs under a second,
    and the whole sweep costs about thirty of them -- so what the chain knows
    about its own limits is measured rather than predicted. The alternative was
    a calculated minimum, which was wrong for the water recycler by 40% and
    which, being stated as a rule, no round ever tested.
    """
    config = _run_config(first_run_dir)
    if not config:
        return None
    agents = _run_agents_config(first_run_dir)
    actor = (agents.get("actor") or {}) if agents else {}
    try:
        constraints = DesignConstraints.from_scenario_config(config)
        bounds = {
            key: float(constraints.bounds[sub]["min"])
            for key, sub in (
                ("plant_sim.ars.capacity_kg_day", "ars"),
                ("plant_sim.ogs.max_o2_kg_day", "ogs"),
                ("plant_sim.wrs.max_feed_l_per_operation", "wrs"),
            )
        }
        measured = measure_survival_limits(
            start=read_capacity_fields(config),
            bounds=bounds,
            runner=scenario_runner(
                scenario_config=config,
                output_root=chain_dir / "survival_limits",
                actor_mode=actor.get("mode"),
                policy_hint=actor.get("policy"),
                steps=steps,
            ),
        )
        write_measured_limits(chain_dir, measured)
        record_measured_limits(chain_dir, measured)
        return measured
    except Exception as exc:  # a measurement that fails must not stop the chain
        (chain_dir / "survival_limits_error.txt").write_text(
            f"{type(exc).__name__}: {exc}", encoding="utf-8"
        )
        return None


def _run_config(run_dir: Path) -> Dict[str, Any]:
    try:
        text = (Path(run_dir) / "scenario_config.yaml").read_text(encoding="utf-8")
        config = yaml.safe_load(text)
    except (OSError, yaml.YAMLError):
        return {}
    return config if isinstance(config, dict) else {}


def _run_agents_config(run_dir: Path) -> Dict[str, Any]:
    try:
        config = yaml.safe_load((Path(run_dir) / "agents_config.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return config if isinstance(config, dict) else {}


def _record_chain_memory(
    chain_dir: Path,
    iteration_dir: Path,
    *,
    iteration: int,
    applied_path: Optional[Path],
) -> None:
    """Fold this round into the note the next round's designer is handed.

    Bookkeeping, not a step of the chain: a memory that cannot be written is
    worth strictly less than the iterations that would be cancelled to report
    it, so the failure is recorded on the iteration and the chain continues.
    """
    applied_keys: Optional[List[str]] = None
    if applied_path is not None and Path(applied_path).exists():
        try:
            applied_keys = capacity_keys_in_document(load_design_proposals(Path(applied_path)))
        except Exception:
            applied_keys = None
    try:
        update_compact_chain_memory(
            chain_dir,
            iteration_dir,
            iteration=iteration,
            applied_capacity_keys=applied_keys,
        )
    except Exception as exc:  # never let the note stop the chain
        (Path(iteration_dir) / "chain_memory_error.txt").write_text(
            f"{type(exc).__name__}: {exc}", encoding="utf-8"
        )


def run_design_iterate(
    *,
    iterations: int,
    chain_dir: Path,
    base_spec: RunSpec,
    recreate: bool = True,
    paired_replay: bool = True,
    reporter: Optional[IterateReporter] = None,
    iteration_record: Optional[Dict[str, Any]] = None,
    measure_limits: bool = True,
) -> Dict[str, Any]:
    """Run *iterations* ssos_eclss_loop sims, applying the accumulated adopted file.

    Generation stays on the unified post-run designer. Run N verifies proposal N-1.
    The last run's newly emitted proposals are recorded but not simulated.
    Verdict comes from paired baseline/final replays.

    The verdict says whether the chain moved; it does not say what to build.
    That comes from :func:`select_chain_final_answer`, which ranks every
    candidate every iteration simulated -- see ``chain_selection`` for why the
    last iteration's preference is not allowed to be the answer on its own.
    """
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    if base_spec.scenario != ITERATE_SCENARIO:
        raise ValueError(f"iterate supports {ITERATE_SCENARIO} only, got {base_spec.scenario!r}")

    chain_dir = prepare_chain_dir(chain_dir, recreate=recreate)
    reporter = reporter or IterateReporter()
    steps = _sim_steps(base_spec)
    accumulated_history: List[Dict[str, Any]] = []
    runs: List[Dict[str, Any]] = []
    stopped_reason: Optional[str] = None
    last_apply_path: Optional[Path] = None
    verified_apply_path: Optional[Path] = None
    requirement_hash: Optional[str] = None
    survival_limits: Optional[Dict[str, Any]] = None

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
            approve_provisional=base_spec.approve_provisional,
            design_history=list(accumulated_history),
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
        # Empty / missing / not-adoptable proposals keep the last applied file
        # (or the initial YAML) so the configured iteration count still runs.
        if proposals_path.exists():
            proposals = load_design_proposals(proposals_path)
            new_changes = list(proposals.get("changes") or [])
            accumulated_history.append({"iteration": index, "changes": new_changes})
            previous_applied = None
            if last_apply_path is not None and last_apply_path.exists():
                try:
                    previous_applied = load_design_proposals(last_apply_path)
                except (OSError, ValueError, TypeError):
                    previous_applied = None
            adoptable = iterate_apply_document(
                proposals,
                approve_provisional=base_spec.approve_provisional,
                installed=_installed_capacity(output_dir),
                previous=previous_applied,
            )
            if adoptable is not None:
                applied_path = output_dir / "applied_proposals.json"
                # Hand on the whole machine, not just the part that changed.
                write_design_proposals(
                    applied_path,
                    complete_capacity_profile(adoptable, row["installed_capacity"]),
                )
                last_apply_path = applied_path
                summary["applied_proposals_path"] = str(applied_path)
                (output_dir / "summary.json").write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        else:
            accumulated_history.append({"iteration": index, "changes": []})
        if index == 1 and measure_limits:
            # Before the second round is designed, so every decision after the
            # first is taken against measurements rather than a calculation.
            reporter.on_phase("measuring survival limits")
            survival_limits = _measure_survival_limits(chain_dir, output_dir, steps=steps)
        _record_chain_memory(
            chain_dir,
            output_dir,
            iteration=index,
            applied_path=apply_this_run,
        )
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
                    approve_provisional=base_spec.approve_provisional,
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

    # Over every iteration that completed, including ones the chain moved on
    # from. A run that stopped early still had iterations before it, and a
    # design found in one of those is still a design.
    final_answer = select_chain_final_answer(
        [Path(str(row["run_dir"])) for row in runs if row.get("exit_code") == 0]
    )
    final_answer_path = write_chain_final_answer(chain_dir, final_answer)

    chain_summary = {
        "scenario": ITERATE_SCENARIO,
        "iterations_requested": iterations,
        "iterations_completed": completed,
        "claim": "unified design applied across chained sims (thresholds not auto-applied)",
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
        "approve_provisional": base_spec.approve_provisional,
        "design_llm": design_llm_provenance(base_spec.overrides),
        "final_answer": {
            "status": final_answer.get("status"),
            "selected_candidate_id": (final_answer.get("selected") or {}).get(
                "chain_candidate_id"
            ),
            "iteration": (final_answer.get("selected") or {}).get("iteration"),
            "fields": (final_answer.get("selected") or {}).get("fields"),
            "crew_remaining": (final_answer.get("selected") or {}).get("crew_remaining"),
            "crew_initial": (final_answer.get("selected") or {}).get("crew_initial"),
            "reason": final_answer.get("reason"),
            "requires_supervisor_approval": final_answer.get("requires_supervisor_approval"),
            "candidates_considered": final_answer.get("candidates_considered"),
            "path": str(final_answer_path),
        },
        "runs": runs,
        "replay_runs": replay_runs,
    }
    if survival_limits:
        chain_summary["survival_limits"] = {
            "status": survival_limits.get("status"),
            "simulations": survival_limits.get("simulations"),
            "smallest_surviving_machine": survival_limits.get("smallest_surviving_machine"),
            "path": str(chain_dir / "measured_limits.json"),
        }
    if iteration_record:
        chain_summary["iteration"] = iteration_record
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
                "final_answer_status": final_answer.get("status"),
                "final_answer_candidate_id": (final_answer.get("selected") or {}).get(
                    "chain_candidate_id"
                ),
                "final_answer_path": str(final_answer_path),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return chain_summary
