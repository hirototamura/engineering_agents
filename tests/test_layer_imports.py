"""Layer import discipline — enforce AGENTS.md dependency direction."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

# Lower layers must not import upper layers (package top-level names under src/).
FORBIDDEN_UPWARD: dict[str, set[str]] = {
    "core": {"environment", "scenario", "tools", "integrations"},
    "environment": {"scenario", "tools", "integrations"},
    "scenario": {"tools"},
    "integrations": {"scenario", "tools", "environment", "core"},
}

# Paths skipped entirely (legacy CLI entrypoints; not layer packages).
SKIP_PREFIXES = (SRC_ROOT / "scripts",)

# Forbidden module name fragments under environment/ (no LLM/Persona in environment).
ENVIRONMENT_FORBIDDEN_MODULES = frozenset(
    {
        "core.agents",
        "core.llm",
        "ollama",
        "persona",
    }
)


def _layer_roots() -> list[Path]:
    return [p for p in SRC_ROOT.iterdir() if p.is_dir() and p.name != "experiments"]


def _package_for_file(path: Path) -> str | None:
    try:
        rel = path.relative_to(SRC_ROOT)
    except ValueError:
        return None
    parts = rel.parts
    if not parts or parts[0] == "experiments":
        return None
    if any(path.is_relative_to(prefix) for prefix in SKIP_PREFIXES):
        return None
    return parts[0]


def _imported_roots(node: ast.AST) -> set[str]:
    roots: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            for alias in child.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(child, ast.ImportFrom):
            if child.module:
                roots.add(child.module.split(".")[0])
    return roots


def _imported_modules(node: ast.AST) -> set[str]:
    mods: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            for alias in child.names:
                mods.add(alias.name)
        elif isinstance(child, ast.ImportFrom) and child.module:
            mods.add(child.module)
    return mods


# core may depend on environment.protocol types only (shared boundary ABCs).
CORE_ALLOWED_ENVIRONMENT_MODULES = frozenset({"environment.protocol"})


def _collect_py_files() -> list[Path]:
    files: list[Path] = []
    for root in _layer_roots():
        files.extend(root.rglob("*.py"))
    return sorted(files)


@pytest.mark.parametrize(
    "py_file", _collect_py_files(), ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_no_upward_layer_imports(py_file: Path):
    package = _package_for_file(py_file)
    if package is None:
        pytest.skip("not a layered package file")
    forbidden = FORBIDDEN_UPWARD.get(package)
    if not forbidden:
        pytest.skip(f"no upward rules for package {package}")

    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    imported = _imported_roots(tree)
    violations = sorted(imported & forbidden)
    if package == "core" and violations == ["environment"]:
        env_mods = {m for m in _imported_modules(tree) if m.startswith("environment.")}
        if env_mods <= CORE_ALLOWED_ENVIRONMENT_MODULES:
            violations = []
    assert not violations, (
        f"{py_file.relative_to(REPO_ROOT)} ({package}/) must not import: {violations}"
    )


def test_environment_has_no_agent_or_llm_imports():
    env_root = SRC_ROOT / "environment"
    if not env_root.is_dir():
        pytest.skip("no environment package")
    violations: list[str] = []
    for py_file in env_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for child in ast.walk(tree):
            mod: str | None = None
            if isinstance(child, ast.Import):
                for alias in child.names:
                    mod = alias.name
                    if any(token in mod for token in ENVIRONMENT_FORBIDDEN_MODULES):
                        violations.append(f"{py_file.relative_to(REPO_ROOT)}: import {mod}")
            elif isinstance(child, ast.ImportFrom) and child.module:
                mod = child.module
                if any(token in mod for token in ENVIRONMENT_FORBIDDEN_MODULES):
                    violations.append(f"{py_file.relative_to(REPO_ROOT)}: from {mod}")
    assert not violations, "environment/ must not import LLM or Persona:\n" + "\n".join(violations)


def test_tools_cli_may_import_scenario():
    """Documented exception: tools/cli -> scenario is allowed (tools -> scenario layer rule)."""
    cli_run = SRC_ROOT / "tools" / "cli" / "commands" / "run.py"
    assert cli_run.is_file()
    tree = ast.parse(cli_run.read_text(encoding="utf-8"))
    imported = _imported_roots(tree)
    assert "scenario" in imported
