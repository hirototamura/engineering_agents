"""Rich terminal output for CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from scenario.jobs.progress import IterateReporter
from scenario.jobs.spec import RunResult
from scenario.ssos_eclss_loop.design_proposals import APPROVE_PROVISIONAL_SIM_INFO

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


_CAPACITY_ORDER = (
    "plant_sim.ars.capacity_kg_day",
    "plant_sim.ogs.max_o2_kg_day",
    "plant_sim.wrs.max_feed_l_per_operation",
)


def _crew_cell(row: Dict[str, Any]) -> str:
    """How many came back, out of how many set out."""
    remaining, initial = row.get("crew_remaining"), row.get("crew_initial")
    if not isinstance(remaining, int):
        return "—"
    if not isinstance(initial, int):
        return str(remaining)
    if remaining == initial:
        return f"[green]{remaining}/{initial}[/green]"
    return f"[red]{remaining}/{initial}[/red]"


def _sizing_cell(row: Dict[str, Any]) -> str:
    """ARS / OGS / WRS as one column, so the score beside it can be read."""
    installed = row.get("installed_capacity")
    if not isinstance(installed, dict) or not installed:
        return "—"
    parts = []
    for key in _CAPACITY_ORDER:
        value = installed.get(key)
        parts.append(
            "—" if not isinstance(value, (int, float)) else f"{round(float(value), 3):g}"
        )
    return " / ".join(parts)


def _score_cells(rows: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """Each round's score and its move, coloured by which way it went.

    The score is the whole point of an iterating run and it was the one number
    the live table did not show: a chain could spend ten rounds getting worse
    and read, from here, exactly like one getting better.
    """
    cells: List[Tuple[str, str]] = []
    previous: Optional[float] = None
    for row in rows:
        score = row.get("evaluation_score")
        if not isinstance(score, (int, float)):
            # Scored is the normal case; say which of the other two it was.
            status = str(row.get("evaluation_status") or "—")
            cells.append((f"[dim]{status}[/dim]", "—"))
            continue
        score = float(score)
        shown = f"{score:.2f}"
        if row.get("paired_replay"):
            # The two replays sit outside the sequence -- they re-run the first
            # and last designs with the designer switched off. Subtracting the
            # last iteration from them would read as another round of movement.
            cells.append((shown, ""))
            continue
        if previous is None:
            delta = "—"
        elif score > previous:
            delta = f"[green]+{score - previous:.2f}[/green]"
        elif score < previous:
            delta = f"[red]{score - previous:.2f}[/red]"
        else:
            delta = "[dim]0.00[/dim]"
        cells.append((shown, delta))
        previous = score
    return cells


def _score_header(rows: List[Dict[str, Any]]) -> str:
    """"Score /100" when every round was marked out of the same total."""
    totals = {
        float(row["evaluation_max_score"])
        for row in rows
        if isinstance(row.get("evaluation_max_score"), (int, float))
    }
    return f"Score /{totals.pop():g}" if len(totals) == 1 else "Score"


def crew_remaining_table(rows: List[Dict[str, Any]]) -> Table:
    table = Table(title="Design iterate — crew remaining and score")
    table.add_column("Iter")
    # Remaining out of the crew that started, so the column carries what "Lost"
    # used to and leaves the width to the two things the run is judged on.
    table.add_column("Crew", justify="right")
    table.add_column("ARS / OGS / WRS", no_wrap=True)
    table.add_column(_score_header(rows), justify="right")
    table.add_column("Δ", justify="right")
    table.add_column("Best", justify="right")
    table.add_column("Props", justify="right")
    # Which round's design this one flew. The filename is always
    # applied_proposals.json, so printing it says nothing.
    table.add_column("Applied from")

    scores = _score_cells(rows)
    # Best so far means best among rounds that brought everyone back. A high
    # score on a round that lost occupants is not a design to steer towards.
    best: Optional[float] = None
    for row, (score_cell, delta_cell) in zip(rows, scores):
        apply_path = row.get("apply_proposals_path")
        apply_name = Path(str(apply_path)).parent.name if apply_path else "—"
        score = row.get("evaluation_score")
        remaining, initial = row.get("crew_remaining"), row.get("crew_initial")
        full_survival = (
            isinstance(remaining, int) and isinstance(initial, int) and remaining == initial
        )
        marker = ""
        if full_survival and isinstance(score, (int, float)) and not row.get("paired_replay"):
            if best is None or float(score) > best:
                best = float(score)
                marker = "[bold green]★[/bold green]"
        table.add_row(
            str(row.get("iteration", "")),
            _crew_cell(row),
            _sizing_cell(row),
            score_cell,
            delta_cell,
            marker or ("[dim]·[/dim]" if best is not None else ""),
            str(row.get("design_proposal_count", "—")),
            apply_name,
        )
    return table


class ChainLiveReporter(IterateReporter):
    """Live table plus iteration/step progress bars for a design→verify chain.

    Used whenever the chain runs — YAML ``iteration.enabled`` or ``--iterate``.
    A single ssos sim reuses the same step bar with ``iterations=1``.
    """

    def __init__(self, *, iterations: int, console: Console) -> None:
        self.iterations = iterations
        self.console = console
        self._rows: List[Dict[str, Any]] = []
        self._run_label = ""
        self._steps = 1
        self.progress = Progress(
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )
        self.iter_task = self.progress.add_task("Iterations", total=max(iterations, 1))
        self.sim_task = self.progress.add_task("Simulation", total=1)
        self._live: Optional[Live] = None

    def _render(self) -> Group:
        return Group(crew_remaining_table(self._rows), self.progress)

    def _ensure_live(self) -> None:
        if self._live is None:
            self._live = Live(
                self._render(),
                console=self.console,
                refresh_per_second=8,
                transient=False,
            )
            self._live.start()

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._render())

    def close(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    def on_run_start(
        self,
        *,
        index: int,
        total: int,
        label: str,
        steps: int,
        kind: str = "iteration",
    ) -> None:
        self._steps = max(steps, 1)
        if kind == "replay":
            self._run_label = f"Replay {label}"
            self.progress.update(self.iter_task, completed=self.iterations, total=max(total, 1))
        else:
            self._run_label = f"Iteration {index}/{total}"
            self.progress.update(
                self.iter_task,
                completed=max(index - 1, 0),
                total=max(total, 1),
            )
        self.progress.reset(self.sim_task, total=self._steps, completed=0)
        self.progress.update(self.sim_task, description=f"{self._run_label}  0/{self._steps} steps")
        self._ensure_live()
        self._refresh()

    def on_step(self, *, step: int, steps: int) -> None:
        total = max(steps, 1)
        completed = min(step + 1, total)
        self._steps = total
        self.progress.update(
            self.sim_task,
            total=total,
            completed=completed,
            description=f"{self._run_label}  {completed}/{total} steps",
        )

    def on_phase(self, detail: str) -> None:
        total = max(self._steps, 1)
        self.progress.update(
            self.sim_task,
            total=total,
            completed=total,
            description=f"{self._run_label}  {detail}",
        )

    def on_run_end(self, row: Dict[str, Any]) -> None:
        self._rows.append(row)
        label = row.get("iteration")
        if isinstance(label, int):
            self.progress.update(self.iter_task, completed=label)
        self._refresh()


def hook_execute_progress(reporter: Optional[IterateReporter]):
    """Adapt ``execute_run`` positional callbacks to :class:`IterateReporter`."""
    if reporter is None:
        return None, None

    def on_step(step: int, steps: int) -> None:
        reporter.on_step(step=step, steps=steps)

    def on_phase(detail: str) -> None:
        reporter.on_phase(detail)

    return on_step, on_phase


def print_chain_summary(
    chain_summary: Dict[str, Any],
    *,
    quiet: bool = False,
    as_json: bool = False,
    skip_runs_table: bool = False,
) -> None:
    if as_json:
        console.print_json(json.dumps(chain_summary, ensure_ascii=False))
        return
    if quiet:
        console.print(str(chain_summary.get("chain_summary_path") or ""))
        return

    if not skip_runs_table:
        rows = list(chain_summary.get("runs") or []) + list(chain_summary.get("replay_runs") or [])
        console.print(crew_remaining_table(rows))
    verdict = chain_summary.get("verdict", "")
    first = chain_summary.get("crew_remaining_first")
    last = chain_summary.get("crew_remaining_last")
    baseline = chain_summary.get("crew_remaining_baseline_replay")
    final_replay = chain_summary.get("crew_remaining_final_replay")
    lines = [
        f"verdict: {verdict}",
        f"crew_remaining first → last: {first} → {last}",
        f"crew_remaining baseline replay → final replay: {baseline} → {final_replay}",
        f"claim: {chain_summary.get('claim')}",
    ]
    if chain_summary.get("stopped_reason"):
        lines.append(f"stopped: {chain_summary['stopped_reason']}")
    console.print(Panel("\n".join(lines), title="Chain", border_style="cyan"))
    print_chain_final_answer(chain_summary)


def print_chain_final_answer(chain_summary: Dict[str, Any]) -> None:
    """The design the chain answers with, or why it has none.

    Shown apart from the verdict on purpose. The verdict is about the chain --
    did it get anywhere -- and a chain can improve without ever reaching a
    design worth building. Printing the two together invites reading the first
    as the second.
    """
    answer = chain_summary.get("final_answer")
    if not isinstance(answer, dict):
        return
    status = str(answer.get("status") or "")
    lines = [f"status: {status}"]
    if answer.get("selected_candidate_id"):
        crew = answer.get("crew_remaining")
        crew_initial = answer.get("crew_initial")
        lines.append(
            f"design: {answer['selected_candidate_id']} "
            f"(iteration {answer.get('iteration')}) keeping {crew}/{crew_initial}"
        )
        fields = answer.get("fields")
        if isinstance(fields, dict):
            lines.append(
                "sizing: " + ", ".join(f"{key} = {value}" for key, value in fields.items())
            )
    if answer.get("reason"):
        lines.append(f"reason: {answer['reason']}")
    considered = answer.get("candidates_considered")
    if considered is not None:
        lines.append(f"chosen from {considered} candidate(s) across the chain")
    if answer.get("requires_supervisor_approval"):
        lines.append("needs a human to approve before it can be applied")
    if answer.get("path"):
        lines.append(str(answer["path"]))
    # Red when the chain has no design to hand over: that is a result to read,
    # not a detail to skim past.
    border = "green" if answer.get("selected_candidate_id") else "red"
    console.print(Panel("\n".join(lines), title="Final answer", border_style=border))


def print_error(message: str, *, hint: Optional[str] = None) -> None:
    body = message if hint is None else f"{message}\n\n{hint}"
    err_console.print(Panel(body, title="Error", border_style="red"))


def print_info(message: str, *, title: str = "INFO") -> None:
    err_console.print(Panel(message, title=title, border_style="blue"))


def maybe_note_approve_provisional(
    *,
    scenario: str,
    approve_provisional: bool,
    quiet: bool,
) -> None:
    """Note auto-approval of LLM designs on ssos_eclss_loop simulations."""
    if quiet or not approve_provisional or scenario != "ssos_eclss_loop":
        return
    print_info(APPROVE_PROVISIONAL_SIM_INFO)


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
