"""Rich terminal output for CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from scenario.jobs.spec import RunResult

console = Console(stderr=False)
err_console = Console(stderr=True)

DASHBOARD_CMD = "python3 -m streamlit run src/tools/dashboard/app.py"


def print_run_plan(
    scenario: str,
    agents_mode: str,
    steps: Optional[int],
    extra_lines: Optional[Dict[str, str]] = None,
) -> None:
    lines = [
        f"agents: {agents_mode}",
        f"steps: {steps if steps is not None else '(from scenario.yaml)'}",
    ]
    for key, value in (extra_lines or {}).items():
        lines.append(f"{key}: {value}")
    console.print(
        Panel(
            "\n".join(lines),
            title=scenario,
            border_style="cyan",
        )
    )


def print_run_result(result: RunResult, *, quiet: bool = False, as_json: bool = False) -> None:
    if as_json:
        console.print_json(json.dumps(result.to_dict(), ensure_ascii=False))
        return
    if quiet:
        console.print(str(result.run_dir))
        return

    if result.exit_code != 0:
        return

    summary = result.summary
    duration = summary.get("duration_wall_s", result.duration_s)
    lines = [f"output: {result.run_dir}", f"duration: {duration:.1f}s"]
    if summary.get("final_co2_ppm") is not None:
        health = (summary.get("final_health") or {}).get("co2_status", "unknown")
        lines.append(f"CO2 final: {summary['final_co2_ppm']} ppm ({health})")
    elif summary.get("final_co2_storage_kg") is not None:
        lines.append(f"CO2 storage final: {summary['final_co2_storage_kg']} kg")
    lines.append(f"view:  {DASHBOARD_CMD}")
    console.print(
        Panel(
            "\n".join(lines),
            title=f"Done ({duration:.1f}s)",
            border_style="green",
        )
    )


def print_error(message: str, *, hint: Optional[str] = None) -> None:
    body = message if hint is None else f"{message}\n\n{hint}"
    err_console.print(Panel(body, title="Error", border_style="red"))


def print_run_list(runs: list[Path]) -> None:
    table = Table(title="Recent runs")
    table.add_column("Run ID")
    table.add_column("Scenario")
    table.add_column("Agents")
    table.add_column("Steps")
    table.add_column("Duration (s)")
    for run_dir in runs:
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        duration = summary.get("duration_wall_s")
        duration_text = f"{duration:.1f}" if isinstance(duration, (int, float)) else "—"
        table.add_row(
            run_dir.name,
            str(summary.get("scenario", "")),
            str(summary.get("agents_mode", "")),
            str(summary.get("steps", "")),
            duration_text,
        )
    console.print(table)
    console.print(f"\nDashboard: {DASHBOARD_CMD}")


def print_doctor_report(report: Dict[str, Any]) -> None:
    lines = []
    for key, value in report.items():
        lines.append(f"{key}: {value}")
    console.print(Panel("\n".join(lines), title="ea doctor", border_style="blue"))
