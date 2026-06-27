"""Inspect run outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from scenario.jobs.resolve import default_results_root
from tools.cli import exit_codes
from tools.cli.output import print_error, print_run_list


def register(app: typer.Typer) -> None:
    app.command("results")(results)


def results(
    run_id: Optional[str] = typer.Argument(None, help="Run id under experiments/results."),
    limit: int = typer.Option(10, "--limit", help="Number of recent runs to list."),
) -> None:
    root = default_results_root()
    if run_id is None:
        runs = _list_runs(root, limit=limit)
        if not runs:
            print_error("No runs found.", hint=f"Expected summaries under: {root}")
            raise typer.Exit(exit_codes.USER_ERROR)
        print_run_list(runs)
        raise typer.Exit(exit_codes.SUCCESS)

    summary_path = root / run_id / "summary.json"
    if not summary_path.exists():
        print_error(f"Run not found: {run_id}", hint=f"Look under: {root}")
        raise typer.Exit(exit_codes.USER_ERROR)
    typer.echo(summary_path.read_text(encoding="utf-8"))
    raise typer.Exit(exit_codes.SUCCESS)


def _list_runs(root: Path, *, limit: int) -> list[Path]:
    if not root.exists():
        return []
    runs = [
        entry
        for entry in root.iterdir()
        if entry.is_dir() and (entry / "summary.json").exists()
    ]
    runs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return runs[:limit]
