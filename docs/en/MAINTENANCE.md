# MkDocs — documentation maintenance

## Scope

- `docs/en/` — English pages (quick start, overview, design docs, SSOS guides, memos)
- `docs/ja/` — Japanese pages (same structure)
- `mkdocs.yml` — site config with `mkdocs-static-i18n` (header language switcher)
- Root `README.md` / `AGENTS.md` — GitHub and Cursor entry hubs (content lives under `docs/{lang}/`)

## Local preview

```bash
pip install -e ".[dev]"
mkdocs serve
# English: http://127.0.0.1:8000/
# Japanese: http://127.0.0.1:8000/ja/
```

Build output `site/` is gitignored. Do not commit it.

## CI

Pull requests run `mkdocs build --strict` (see `.github/workflows/docs.yml`). Code quality gates live in `.github/workflows/ci.yml` (ruff + pytest). Local mirror: `./scripts/ci-local.sh`.

Main merges also trigger docs deploy to the `docs/ssos-mkdocs` branch (`.github/workflows/docs-deploy.yml`).

When updating SSOS or scrubber backend docs, verify file paths against `src/environment/` — ECLSS lives under `ssos/eclss/`, scrubber EPS under `scrubber/eps/`, and SSOS EPS bridge under `ssos/eps/ros2/` (post–environment refactor).

## Governance calendar

| Cadence | Work |
| --- | --- |
| Every PR | `ci` + `mkdocs` workflows green |
| Monthly | Review Dependabot PRs |
| Quarterly | Review `.cursor/` assets (rules, agents, skills) against AGENTS.md — fix Cursor side, do not duplicate policy |
| SSOS image update | Bump `SSOS_IMAGE_DIGEST` in `.github/workflows/ssos-regression.yml` |

## References

- [Document catalog](catalog.md) — full page index including memos not in the main nav
- [Contributing](CONTRIBUTING.md)
- [SSOS connection plan](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md)
- [SSOS roadmap](ssos/roadmap.md)
