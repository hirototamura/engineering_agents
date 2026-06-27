"""Environment checks for CLI users."""

from __future__ import annotations

import platform
import sys

import typer

from core.llm.ollama import resolve_ollama_base_url
from scenario.jobs.resolve import RESULTS_ROOT_ENV_VAR, default_results_root
from tools.cli import exit_codes
from tools.cli.output import print_doctor_report


def register(app: typer.Typer) -> None:
    app.command("doctor")(doctor)


def doctor() -> None:
    report = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "results_root": str(default_results_root()),
        "results_root_env": RESULTS_ROOT_ENV_VAR,
    }

    try:
        import numpy  # noqa: F401
        import yaml  # noqa: F401

        report["dependencies"] = "ok"
    except ImportError as exc:
        report["dependencies"] = f"missing: {exc.name}"

    ollama_url = resolve_ollama_base_url()
    report["ollama_url"] = ollama_url
    try:
        import requests

        response = requests.get(f"{ollama_url}/api/tags", timeout=2)
        response.raise_for_status()
        report["ollama"] = "reachable"
    except Exception as exc:
        report["ollama"] = f"unreachable ({exc.__class__.__name__})"

    print_doctor_report(report)
    raise typer.Exit(exit_codes.SUCCESS)
