"""RunSpec-based job commands for local and future cluster workers."""

from __future__ import annotations

from pathlib import Path

import typer

from scenario.jobs.executor import execute_run
from scenario.jobs.spec import RunSpec
from tools.cli import exit_codes
from tools.cli.output import print_error, print_run_result


def register(app: typer.Typer) -> None:
    job_app = typer.Typer(help="RunSpec job utilities.")
    job_app.command("run")(job_run)
    app.add_typer(job_app, name="job")


def job_run(
    spec_path: Path = typer.Argument(..., help="Path to a RunSpec JSON file."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    quiet: bool = typer.Option(False, "--quiet", help="Print only the output path."),
) -> None:
    if not spec_path.exists():
        print_error(f"RunSpec not found: {spec_path}")
        raise typer.Exit(exit_codes.USER_ERROR)

    spec = RunSpec.read_json(spec_path)
    result = execute_run(spec)
    print_run_result(result, quiet=quiet, as_json=json_output)
    if result.exit_code != 0:
        print_error(result.error or "Simulation failed.")
        raise typer.Exit(result.exit_code)
    raise typer.Exit(exit_codes.SUCCESS)
