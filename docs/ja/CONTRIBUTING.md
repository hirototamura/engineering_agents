# Contributing

人間・エージェント向けの薄い入口です。**本格的な規律:** [AGENTS.md](AGENTS.md)。

## セットアップ

**Python 3.11+** 必須（`pyproject.toml` の `requires-python`）。

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python3 -m tools.cli doctor   # ローカルのみ — CI では実行しない
```

`~/.local/bin` が PATH に無い場合は `ea` より `python3 -m tools.cli …` を推奨。[cli.md](cli.md) 参照。

## PR 前の検証

```bash
./scripts/ci-local.sh
```

GitHub Actions のミラー:

- `.github/workflows/ci.yml` — ruff + pytest（`tests/tools/` 含む）+ レイヤー/日英 docs/検証規律テスト
- `.github/workflows/docs.yml` — `mkdocs build --strict`

ブランチ保護では **`ci`** と **`mkdocs`** の両方を必須にする。

## 閉ループ smoke（任意）

`ssos_eclss_loop` + `mock` + `labeled_rule_base` の 2-run `--apply-proposals` は [AGENTS.md](AGENTS.md)（Cursor Cloud 節）参照。

## Cloud Agent ブランチ

自律エージェント PR は `cursor/<descriptive-name>-e5ff`。
