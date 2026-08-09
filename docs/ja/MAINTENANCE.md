# MkDocs — ドキュメント保守ガイド

## スコープ

- `docs/ja/` — 日本語ページ（クイックスタート、概要、設計 doc、SSOS 運用ガイド、memo）
- `docs/en/` — 英語ページ（同一構成）
- `mkdocs.yml` — `mkdocs-static-i18n` による言語切替設定
- ルート `README.md` / `AGENTS.md` — GitHub・Cursor 向け入口（本文は `docs/{lang}/`）

## ローカルプレビュー

```bash
pip install -e ".[dev]"
mkdocs serve
# 日本語: http://127.0.0.1:8000/ja/
# English: http://127.0.0.1:8000/
```

ビルド成果物 `site/` は `.gitignore` 済み。コミットしない。

## CI

PR では `mkdocs build --strict` を実行（`.github/workflows/docs.yml`）。コード品質は `.github/workflows/ci.yml`（ruff + pytest）。ローカルミラー: `./scripts/ci-local.sh`。

main マージ時は `docs/ssos-mkdocs` ブランチへ docs deploy（`.github/workflows/docs-deploy.yml`）。

SSOS / scrubber バックエンドのドキュメントを更新するときは、`src/environment/` の実パスと照合すること — ECLSS は `ssos/eclss/`、scrubber EPS は `scrubber/eps/`、SSOS EPS ブリッジは `ssos/eps/ros2/`（environment リファクタ後）。

## ガバナンス

| 頻度 | 作業 |
| --- | --- |
| PR 毎 | `ci` と `mkdocs` workflow が green |
| 月次 | Dependabot PR の確認 |
| 四半期 | `.cursor/`（rules / agents / skills）が AGENTS.md と矛盾していないか確認 — 直すのは Cursor 側 |
| SSOS イメージ更新時 | `.github/workflows/ssos-regression.yml` の digest ピン更新 |

## 参照

- [ドキュメント索引](catalog.md) — メインナビ外の memo も含む全ページ一覧
- [Contributing](CONTRIBUTING.md)
- [SSOS ECLSS 接合プラン](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md)
- [SSOS ロードマップ](ssos/roadmap.md)
