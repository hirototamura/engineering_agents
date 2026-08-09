# Contributing

Thin entry point for humans and agents. **Full engineering discipline:** [AGENTS.md](AGENTS.md).

## Setup

Requires **Python 3.11+** (`requires-python` in `pyproject.toml`).

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python3 -m tools.cli doctor   # local only — not run in CI
```

Prefer `python3 -m tools.cli …` over `ea` when `~/.local/bin` is not on `PATH`. See [cli.md](cli.md).

## Verify before PR

```bash
./scripts/ci-local.sh
```

This mirrors GitHub Actions:

- `.github/workflows/ci.yml` — ruff + pytest (incl. `tests/tools/`) + layer/bilingual/verification tests
- `.github/workflows/docs.yml` — `mkdocs build --strict`

Branch protection should require both **`ci`** and **`mkdocs`** status checks.

## Closed-loop smoke (optional)

`ssos_eclss_loop` with mock backend and `labeled_rule_base` — see [AGENTS.md](AGENTS.md) (Cursor Cloud section) for the 2-run `--apply-proposals` flow.

## Branch protection (maintainers)

On GitHub: **Settings → Branches → main** → require status checks **`ci`** (workflow **CI**) and **`mkdocs`** (workflow **Docs**).

## Cloud Agent branches

Use `cursor/<descriptive-name>-e5ff` for autonomous agent PRs.
