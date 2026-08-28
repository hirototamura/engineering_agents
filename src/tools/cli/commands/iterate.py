"""Iterate command — chain ssos_eclss_loop design→verify runs."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from scenario.jobs.iterate import (
    ALLOWED_ITERATE_BACKENDS,
    ITERATE_SCENARIO,
    run_design_iterate,
)
from scenario.jobs.resolve import default_results_root, sanitize_run_id
from scenario.jobs.spec import RunSpec
from scenario.runner import scenario_descriptions
from tools.cli import exit_codes
from tools.cli.commands import run as run_cmd
from tools.cli.output import ChainLiveReporter, console, print_chain_summary, print_error, print_run_plan
from tools.cli.overrides import merge_overrides

DEFAULT_RUN_ID = "ssos_eclss_loop_design_iter"


def register(app: typer.Typer) -> None:
    app.command("iterate")(iterate)


def iterate(
    scenario: Optional[str] = typer.Argument(
        None,
        help="Scenario name (only ssos_eclss_loop is supported).",
    ),
    iterations: int = typer.Option(10, "--iterations", min=1, max=50, help="Number of simulations."),
    actor_mode: Optional[str] = typer.Option(
        None,
        "--actor-mode",
        help="Actor mode. Default: labeled_rule_base.",
    ),
    design_mode: Optional[str] = typer.Option(
        None,
        "--design-mode",
        help="Design mode. Default: llm.",
    ),
    agents_mode: Optional[str] = typer.Option(
        None,
        "--agents-mode",
        help="Deprecated alias for --actor-mode.",
    ),
    steps: Optional[int] = typer.Option(None, "--steps", help="Override simulation.steps."),
    run_id: Optional[str] = typer.Option(
        None,
        "--run-id",
        help=f"Parent directory under results (default: {DEFAULT_RUN_ID}).",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        help="Explicit parent directory for the chain.",
    ),
    results_root: Optional[Path] = typer.Option(
        None,
        "--results-root",
        help="Override results base directory.",
    ),
    backend: Optional[str] = typer.Option(
        None,
        "--backend",
        help="mock or plant_sim. Default: plant_sim. ros2 is rejected.",
    ),
    llm_provider: Optional[str] = typer.Option(None, "--llm-provider"),
    llm_model: Optional[str] = typer.Option(None, "--llm-model"),
    inject_failures: Optional[bool] = typer.Option(
        None,
        "--inject-failures/--no-inject-failures",
        help="Subsystem failure schedule. Default: on.",
    ),
    paired_replay: bool = typer.Option(
        True,
        "--paired-replay/--no-paired-replay",
        help="After the chain, re-run baseline vs final design (verdict source). Default: on.",
    ),
    seed: Optional[int] = typer.Option(None, "--seed"),
    set_values: List[str] = typer.Option([], "--set"),
    override_file: Optional[Path] = typer.Option(None, "--override-file"),
    no_recreate: bool = typer.Option(False, "--no-recreate"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_output: bool = typer.Option(False, "--json"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    scenario_name = scenario or ITERATE_SCENARIO
    known = scenario_descriptions()
    if scenario_name not in known:
        names = ", ".join(sorted(known))
        print_error(f"Unknown scenario: {scenario_name!r}.", hint=f"Available: {names}")
        raise typer.Exit(exit_codes.USER_ERROR)
    if scenario_name != ITERATE_SCENARIO:
        print_error(
            f"iterate supports {ITERATE_SCENARIO} only.",
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
        overrides = _apply_iterate_defaults(
            overrides,
            actor_mode=actor_mode,
            agents_mode=agents_mode,
            design_mode=design_mode,
            backend=backend,
            inject_failures=inject_failures,
        )
        overrides = run_cmd._apply_llm_cli_to_llm_sides(
            scenario_name, overrides, llm_provider=llm_provider, llm_model=llm_model
        )
        overrides = run_cmd._materialize_resolved_llm(scenario_name, overrides)
        run_cmd._validate_merged_overrides(overrides)
        _validate_iterate_backend(overrides)
    except ValueError as exc:
        print_error(str(exc), hint="Example: --backend plant_sim --iterations 10")
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
    )

    resolved_mode = run_cmd._resolved_display_mode(scenario_name, overrides)
    resolved_steps = (overrides or {}).get("simulation", {}).get("steps")
    extra_lines = {
        "iterations": str(iterations),
        "backend": str(((overrides or {}).get("backend") or {}).get("kind")),
        "inject_failures": str((overrides or {}).get("inject_failures")),
        "paired_replay": str(paired_replay).lower(),
        "chain_dir": str(parent),
        "claim": "controller-policy adaptation",
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
    raise typer.Exit(exit_codes.SUCCESS)


def _apply_iterate_defaults(
    overrides: dict | None,
    *,
    actor_mode: Optional[str],
    agents_mode: Optional[str],
    design_mode: Optional[str],
    backend: Optional[str],
    inject_failures: Optional[bool],
) -> dict:
    merged = dict(overrides or {})
    if backend is None and not ((merged.get("backend") or {}).get("kind")):
        merged = merge_overrides(merged, {"backend": {"kind": "plant_sim"}}) or {}
    if actor_mode is None and agents_mode is None:
        existing = ((merged.get("agents") or {}).get("actor") or {}).get("mode")
        if existing is None:
            merged = merge_overrides(merged, {"agents": {"actor": {"mode": "labeled_rule_base"}}}) or {}
    if design_mode is None:
        existing = ((merged.get("agents") or {}).get("design") or {}).get("mode")
        if existing is None:
            merged = merge_overrides(merged, {"agents": {"design": {"mode": "llm"}}}) or {}
    if inject_failures is None and "inject_failures" not in merged:
        merged = merge_overrides(merged, {"inject_failures": True}) or {}
    return merged


def _validate_iterate_backend(overrides: dict | None) -> None:
    kind = ((overrides or {}).get("backend") or {}).get("kind")
    if kind not in ALLOWED_ITERATE_BACKENDS:
        allowed = ", ".join(sorted(ALLOWED_ITERATE_BACKENDS))
        raise ValueError(
            f"iterate backend must be one of: {allowed}. Got {kind!r} "
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
