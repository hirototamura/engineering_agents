"""List available scenarios."""

from __future__ import annotations

import typer
from rich.table import Table

from scenario.runner import scenario_descriptions
from tools.cli.output import console


def register(app: typer.Typer) -> None:
    app.command("scenarios")(scenarios)


def scenarios() -> None:
    descriptions = scenario_descriptions()
    table = Table(title="Scenarios")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    for name in sorted(descriptions):
        table.add_row(name, descriptions[name])
    console.print(table)
