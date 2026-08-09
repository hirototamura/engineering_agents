"""Bilingual doc pairs — en/ja files listed in mkdocs nav / maintenance scope must both exist."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"

# Explicit pairs for primary docs (folder-based i18n under docs/{en,ja}/).
REQUIRED_PAIRS: list[tuple[str, str]] = [
    ("en/index.md", "ja/index.md"),
    ("en/overview.md", "ja/overview.md"),
    ("en/AGENTS.md", "ja/AGENTS.md"),
    ("en/cli.md", "ja/cli.md"),
    ("en/architecture.md", "ja/architecture.md"),
    ("en/api-contracts.md", "ja/api-contracts.md"),
    ("en/development-plan.md", "ja/development-plan.md"),
    ("en/one-piece-integration.md", "ja/one-piece-integration.md"),
    ("en/scenario-scrubber-degradation.md", "ja/scenario-scrubber-degradation.md"),
    ("en/scenario-ssos-eclss-loop.md", "ja/scenario-ssos-eclss-loop.md"),
    ("en/MAINTENANCE.md", "ja/MAINTENANCE.md"),
    ("en/CONTRIBUTING.md", "ja/CONTRIBUTING.md"),
    ("en/ssos/index.md", "ja/ssos/index.md"),
    ("en/ssos/quickstart.md", "ja/ssos/quickstart.md"),
    ("en/ssos/eclss-integration.md", "ja/ssos/eclss-integration.md"),
    ("en/ssos/eps-integration.md", "ja/ssos/eps-integration.md"),
    ("en/ssos/scenario-eclss-loop.md", "ja/ssos/scenario-eclss-loop.md"),
    ("en/ssos/troubleshooting.md", "ja/ssos/troubleshooting.md"),
    ("en/ssos/roadmap.md", "ja/ssos/roadmap.md"),
    ("en/ssos/api-reference.md", "ja/ssos/api-reference.md"),
]


def _nav_md_paths() -> set[str]:
    """Collect markdown paths from mkdocs-static-i18n nav (relative, no locale prefix)."""
    text = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    paths: set[str] = set()
    for match in re.finditer(r":\s+([A-Za-z0-9_./-]+\.md)\s*$", text, re.MULTILINE):
        path = match.group(1)
        if path.startswith(("http://", "https://")):
            continue
        paths.add(path)
    return paths


@pytest.mark.parametrize("en_rel,ja_rel", REQUIRED_PAIRS)
def test_required_bilingual_pair_exists(en_rel: str, ja_rel: str):
    en_path = DOCS / en_rel
    ja_path = DOCS / ja_rel
    assert en_path.is_file(), f"missing {en_path}"
    assert ja_path.is_file(), f"missing {ja_path}"


def test_mkdocs_nav_pages_exist_in_both_locales():
    """Nav entries (locale-relative) must exist under docs/en and docs/ja."""
    nav_paths = _nav_md_paths()
    # Skip memo-only / language-specific orphans; require shared top-level nav pages.
    shared_roots = {
        "index.md",
        "overview.md",
        "architecture.md",
        "api-contracts.md",
        "cli.md",
        "AGENTS.md",
        "development-plan.md",
        "MAINTENANCE.md",
        "scenario-scrubber-degradation.md",
        "scenario-ssos-eclss-loop.md",
    }
    missing: list[str] = []
    for rel in sorted(nav_paths & shared_roots):
        for locale in ("en", "ja"):
            path = DOCS / locale / rel
            if not path.is_file():
                missing.append(str(path.relative_to(REPO_ROOT)))
    assert not missing, "mkdocs nav pages missing in a locale:\n" + "\n".join(missing)
