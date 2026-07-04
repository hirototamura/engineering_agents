"""Verification discipline — no LLM subjective pass/fail in health checkers."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"

# Pure health / verification modules must not reference LLM clients.
HEALTH_CHECKER_FILES = [
    SRC / "environment" / "scrubber" / "eclss_ops" / "telemetry.py",
    SRC / "scenario" / "ssos_eclss_loop" / "health.py",
]

# Scenario teams may use LLM for design/deliberation — not checked here.
ALLOW_LLM_PATH_PREFIXES = (
    SRC / "scenario" / "agents",
    SRC / "core" / "llm",
    SRC / "core" / "agents",
)


def _references_ollama(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "ollama" in node.module:
            hits.append(f"from {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "ollama" in alias.name:
                    hits.append(f"import {alias.name}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in {"OllamaClient"}:
                hits.append("OllamaClient(...)")
            elif isinstance(func, ast.Attribute) and func.attr in {"complete", "chat"}:
                if isinstance(func.value, ast.Name) and "llm" in func.value.id.lower():
                    hits.append(f"{func.value.id}.{func.attr}(...)")
    return hits


@pytest.mark.parametrize("path", HEALTH_CHECKER_FILES)
def test_health_checkers_do_not_use_llm(path: Path):
    if not path.is_file():
        pytest.skip(f"missing {path}")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits = _references_ollama(tree)
    assert not hits, f"{path.relative_to(REPO_ROOT)} must not use LLM for verification: {hits}"


def test_scenario_agents_may_use_ollama_only_under_agents_package():
    """Sanity: LLM imports exist only where deliberation is expected."""
    unexpected: list[str] = []
    for py_file in SRC.rglob("*.py"):
        if any(str(py_file).startswith(str(p)) for p in ALLOW_LLM_PATH_PREFIXES):
            continue
        if py_file in HEALTH_CHECKER_FILES:
            continue
        if "environment" in py_file.parts:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            if _references_ollama(tree):
                unexpected.append(str(py_file.relative_to(REPO_ROOT)))
    assert not unexpected, "Ollama outside allowed packages:\n" + "\n".join(unexpected)
