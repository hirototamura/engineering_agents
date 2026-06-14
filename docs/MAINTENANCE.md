# SSOS MkDocs — ドキュメント保守ブランチ向けガイド

**ブランチ**: `docs/ssos-mkdocs`（実装は `feat/ssos-eclss-loop` と分離）

## スコープ

このブランチで扱うもの:

- `docs/ssos/` — SSOS ECLSS + EPS 接合の運用・レビュー用ドキュメント
- `docs/catalog.md`, `docs/index.md` — MkDocs ナビ・カタログ
- `mkdocs.yml` — サイト設定
- `pyproject.toml` の `[project.optional-dependencies] docs`（MkDocs 依存）

**ここに含めないもの**（別 PR / `feat/ssos-eclss-loop`）:

- `src/` のブリッジ・シナリオ実装
- `memo/ssos_eclss_loop_connection_plan.md` の実装プラン更新（統合ブランチ側）

統合コードの正本は `feat/ssos-eclss-loop`。ドキュメントは実装のコミット SHA を参照し、必要なら cherry-pick や手動同期で追従する。

## ローカルプレビュー

```bash
git checkout docs/ssos-mkdocs
pip install -e ".[dev,docs]"
mkdocs serve
```

ビルド成果物 `site/` は `.gitignore` 済み。コミットしない。

## PR 方針

- **統合 PR に MkDocs 変更を混ぜない** — レビュー対象を「実装」と「ドキュメント」で分ける
- 実装マージ後、`docs/ssos-mkdocs` を `main`（または統合ブランチ）へ rebase / merge してから docs 専用 PR を出す
- CI で `mkdocs build --strict` を足す場合もこのブランチで行う

## 参照

- 実装プラン（メモ）: `feat/ssos-eclss-loop` 上の `memo/ssos_eclss_loop_connection_plan.md`
- ロードマップ本文: [docs/ssos/roadmap.md](ssos/roadmap.md)
