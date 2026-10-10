"""Mechanical run command adapter; existing ECLSS CLI behavior is untouched."""
from __future__ import annotations

import json
from pathlib import Path

import typer


def run_mechanical(*, iterate=None, backend=None, output_dir=None, run_id=None,
                   results_root=None, agents_mode=None, design_mode=None,
                   llm_provider=None, llm_model=None, seed=None, set_values=(),
                   override_file=None, apply_proposals=None, dry_run=False,
                   write_spec=None, json_output=False, quiet=False, **unused):
    from tools.cli.overrides import load_override_file, merge_overrides, parse_set_values
    from scenario.jobs.spec import RunSpec
    from scenario.jobs.executor import execute_run
    from scenario.runner import load_scenario_config
    from tools.cli.output import print_error, print_run_result
    try:
        if seed is not None:
            raise ValueError("Mechanical seeds are frozen in SSOT; --seed cannot override evaluation conditions")
        overrides = merge_overrides(load_override_file(override_file) if override_file else {},
                                    parse_set_values(set_values) if set_values else {}) or {}
        if backend:
            backend = {"cpu": "mujoco_cpu", "gpu": "mjx_gpu"}.get(backend, backend)
            if backend not in {"mujoco_cpu", "mjx_gpu"}:
                raise ValueError("balancing_cube backend must be mujoco_cpu or mjx_gpu")
            overrides.setdefault("backend", {})["kind"] = backend
        if iterate is not None:
            overrides.setdefault("iteration", {})["count"] = iterate
        if agents_mode or design_mode:
            overrides.setdefault("agents", {})["mode"] = design_mode or agents_mode
        if llm_provider or llm_model:
            llm = overrides.setdefault("agents", {}).setdefault("llm", {})
            if llm_provider:
                llm["provider"] = llm_provider
            if llm_model:
                llm["model"] = llm_model
        # All physics and verification overrides must enter through an approved
        # SSOT revision, never via the convenience CLI's --set escape hatch.
        allowed = {"ssot", "backend", "agents", "iteration", "output"}
        if set(overrides) - allowed:
            raise ValueError("Mechanical CLI overrides may configure ssot/backend/agents/budget only")
        resolved = load_scenario_config("balancing_cube", overrides)
        if resolved["backend"]["kind"] not in {"cpu", "gpu", "mujoco_cpu", "mjx_gpu"}:
            raise ValueError("Unsupported mechanical backend")
        budget = resolved["iteration"]
        if not (1 <= budget["count"] <= 5 and 1 <= budget["max_candidates"] <= 20
                and 0 < budget["max_wall_s"] <= 1800 and 1 <= budget["stagnation_rounds"] <= 3):
            raise ValueError("Mechanical budget limits: 5 rounds, 20 candidates, 1800 seconds, 3 stagnant rounds")
        if not resolved["ssot"].get("path"):
            raise ValueError("Set --set ssot.path=/path/to/onepiece-store")
        spec = RunSpec(scenario="balancing_cube", overrides=overrides, output_dir=output_dir,
                       run_id=run_id, results_root=results_root, recreate_output=False,
                       seed=seed, apply_proposals_path=apply_proposals)
        if write_spec:
            spec.write_json(write_spec)
        if dry_run:
            typer.echo(spec.to_json() if json_output else json.dumps(resolved))
            return
        result = execute_run(spec)
        print_run_result(result, quiet=quiet, as_json=json_output)
        if result.exit_code:
            raise typer.Exit(result.exit_code)
    except (ValueError, KeyError) as error:
        print_error(str(error))
        raise typer.Exit(2) from error
