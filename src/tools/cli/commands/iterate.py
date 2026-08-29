"""Chained design→verify execution used by `ea run --iterate`."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from scenario.jobs.iterate import (
    ALLOWED_ITERATE_BACKENDS,
    ITERATE_SCENARIO,
    run_design_iterate,
)
from scenario.jobs.resolve import default_results_root, sanitize_run_id
from scenario.jobs.spec import RunSpec
from scenario.runner import load_scenario_config
from scenario.ssos_eclss_loop.subsystem_failures import resolve_inject_subsystem_failures
from tools.cli import exit_codes
from tools.cli.commands import run as run_cmd
from tools.cli.output import ChainLiveReporter, console, print_chain_summary, print_error, print_run_plan

DEFAULT_RUN_ID = "ssos_eclss_loop_design_iter"


def run_iterate_from_run(
    *,
    scenario_name: str,
    iterations: int,
    actor_mode: Optional[str],
    design_mode: Optional[str],
    agents_mode: Optional[str],
    steps: Optional[int],
    run_id: Optional[str],
    output_dir: Optional[Path],
    results_root: Optional[Path],
    backend: Optional[str],
    llm_provider: Optional[str],
    llm_model: Optional[str],
    inject_failures: Optional[bool],
    paired_replay: bool,
    approve_provisional: bool,
    iteration_record: Optional[Dict[str, Any]] = None,
    seed: Optional[int],
    set_values: List[str],
    override_file: Optional[Path],
    no_recreate: bool,
    dry_run: bool,
    write_spec: Optional[Path],
    json_output: bool,
    quiet: bool,
) -> None:
    if scenario_name != ITERATE_SCENARIO:
        print_error(
            f"--iterate supports {ITERATE_SCENARIO} only.",
            hint="scrubber_degradation does not re-inject design proposals.",
        )
        raise typer.Exit(exit_codes.USER_ERROR)

    try:
        overrides = run_cmd._build_overrides(
            scenario_name=scenario_name,
            agents_mode=agents_mode,
            actor_mode=actor_mode,
            design_mode=design_mode,
            steps=steps,
            backend=backend,
            inject_failures=inject_failures,
            llm_provider=llm_provider,
            llm_model=llm_model,
            set_values=set_values,
            override_file=override_file,
        )
        overrides = run_cmd._apply_cli_defaults(scenario_name, overrides)
        overrides = run_cmd._apply_llm_cli_to_llm_sides(
            scenario_name, overrides, llm_provider=llm_provider, llm_model=llm_model
        )
        overrides = run_cmd._materialize_resolved_llm(scenario_name, overrides)
        run_cmd._validate_merged_overrides(overrides)
        _validate_iterate_backend(overrides)
    except ValueError as exc:
        print_error(str(exc), hint="Example: ea run ssos_eclss_loop --iterate 10 --backend plant_sim")
        raise typer.Exit(exit_codes.USER_ERROR) from exc

    parent = _resolve_chain_dir(
        output_dir=output_dir,
        results_root=results_root,
        run_id=run_id,
    )
    spec = RunSpec(
        scenario=scenario_name,
        overrides=overrides,
        seed=seed,
        approve_provisional=approve_provisional,
    )
    if write_spec is not None:
        spec.write_json(write_spec)

    resolved_mode = run_cmd._resolved_display_mode(scenario_name, overrides)
    resolved_steps = (overrides or {}).get("simulation", {}).get("steps")
    resolved_config = load_scenario_config(scenario_name, overrides)
    extra_lines = {
        "iterate": str(iterations),
        "backend": str(((overrides or {}).get("backend") or {}).get("kind")),
        "inject_failures": str(resolve_inject_subsystem_failures(resolved_config)).lower(),
        "paired_replay": str(paired_replay).lower(),
        "approve_provisional": str(approve_provisional).lower(),
        "chain_dir": str(parent),
        "claim": "chained unified design (thresholds not auto-applied)",
    }
    if not quiet and not json_output:
        print_run_plan(
            scenario_name,
            str(resolved_mode),
            int(resolved_steps) if resolved_steps is not None else None,
            extra_lines=extra_lines,
        )

    if dry_run:
        if json_output:
            typer.echo(spec.to_json())
        else:
            typer.echo(str(parent))
        raise typer.Exit(exit_codes.SUCCESS)

    if run_cmd._any_llm_mode(scenario_name, overrides):
        env_code = run_cmd._preflight_llm(scenario_name, overrides)
        if env_code != exit_codes.SUCCESS:
            raise typer.Exit(env_code)

    live: ChainLiveReporter | None = None
    if not quiet and not json_output:
        typer.echo(f"Running {iterations} chained simulations...")
        live = ChainLiveReporter(iterations=iterations, console=console)

    try:
        chain_summary = run_design_iterate(
            iterations=iterations,
            chain_dir=parent,
            base_spec=spec,
            recreate=not no_recreate,
            paired_replay=paired_replay,
            reporter=live,
            iteration_record=iteration_record,
        )
    finally:
        if live is not None:
            live.close()
    print_chain_summary(
        chain_summary,
        quiet=quiet,
        as_json=json_output,
        skip_runs_table=live is not None,
    )
    code = chain_exit_code(chain_summary)
    if code != exit_codes.SUCCESS:
        print_error(str(chain_summary.get("stopped_reason") or "Iterate chain failed."))
        raise typer.Exit(code)
    raise typer.Exit(exit_codes.SUCCESS)


def chain_exit_code(chain_summary: Dict[str, Any]) -> int:
    """Non-zero when a chained sim or replay failed, or the chain aborted early."""
    rows = list(chain_summary.get("runs") or []) + list(chain_summary.get("replay_runs") or [])
    if any(int(row.get("exit_code") or 0) != 0 for row in rows):
        return exit_codes.RUN_FAILURE
    requested = int(chain_summary.get("iterations_requested") or 0)
    completed = int(chain_summary.get("iterations_completed") or 0)
    if requested > 0 and completed < requested:
        return exit_codes.RUN_FAILURE
    return exit_codes.SUCCESS


def _validate_iterate_backend(overrides: dict | None) -> None:
    kind = ((overrides or {}).get("backend") or {}).get("kind")
    if kind not in ALLOWED_ITERATE_BACKENDS:
        allowed = ", ".join(sorted(ALLOWED_ITERATE_BACKENDS))
        raise ValueError(
            f"--iterate backend must be one of: {allowed}. Got {kind!r} "
            "(ros2 would bypass the host container path)."
        )


def _resolve_chain_dir(
    *,
    output_dir: Optional[Path],
    results_root: Optional[Path],
    run_id: Optional[str],
) -> Path:
    if output_dir is not None:
        return Path(output_dir)
    root = results_root or default_results_root()
    return root / sanitize_run_id(run_id or DEFAULT_RUN_ID)
