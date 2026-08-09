#!/usr/bin/env bash
# Local CI mirror — pytest/ruff gates from ci.yml + docs strict from docs.yml
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
python3 -m pip install -e ".[dev]" -q
python3 -m ruff check src tests
python3 -m ruff format --check src tests
python3 -m mkdocs build --strict
python3 -m pytest -q --ignore=tests/e2e
python3 -m pytest -q tests/e2e/test_ssos_regression.py::test_regression_tier1_pytest_only
python3 -m pytest -q tests/test_layer_imports.py tests/test_docs_bilingual_pairs.py tests/test_verification_discipline.py
