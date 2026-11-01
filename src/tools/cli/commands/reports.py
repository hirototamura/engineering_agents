"""Workspace report-library entry point, kept outside simulation layers."""
from pathlib import Path

import typer


def register(app: typer.Typer) -> None:
    @app.command("reports", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
    def reports(
        ctx: typer.Context,
        action: str = typer.Argument("build", help="build, serve, translate, capture or verify"),
        workspace: Path | None = typer.Option(None, "--workspace", help="workspace containing report project folders"),
    ) -> None:
        from tools.report_library.__main__ import main
        arguments = (["--workspace", str(workspace)] if workspace else []) + [action, *ctx.args]
        main(arguments)
