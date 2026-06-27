# MkDocs — ドキュメント保守ガイド

## スコープ

- `docs/ja/` — 日本語（README、AGENTS、設計 doc、SSOS 運用ガイド、memo）
- `docs/en/` — 英語（README、AGENTS、設計 doc、memo）
- `docs/index.md`, `docs/catalog.md` — MkDocs ナビ・カタログ
- `mkdocs.yml` — サイト設定
- ルート `README.md` / `AGENTS.md` — GitHub・Cursor 向けの言語ハブ（本文は `docs/{lang}/`）

## ローカルプレビュー

```bash
pip install -e ".[dev]"
mkdocs serve
# → http://127.0.0.1:8000/
```

ビルド成果物 `site/` は `.gitignore` 済み。コミットしない。

## 参照

- 実装プラン: [docs/ja/memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](docs/ja/memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md)
- SSOS ロードマップ: [ja/ssos/roadmap.md](ja/ssos/roadmap.md)
