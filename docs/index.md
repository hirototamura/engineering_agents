# Engineering Agents — ドキュメント

ECLSS レジリエンス・ループと SSOS 接合のドキュメントへようこそ。

**→ [ドキュメント索引](catalog.md)** — 全ページ一覧

## クイックスタート

```bash
pip install -e ".[dev]"
mkdocs serve
# http://127.0.0.1:8000/
```

静的 HTML を生成する場合:

```bash
mkdocs build
# 出力: site/
```

## 主要セクション

| セクション | 説明 |
| --- | --- |
| [日本語 — 概要](ja/README.md) | セットアップ、ダッシュボード、実行手順 |
| [日本語 — アーキテクチャ](ja/architecture.md) | レイヤ構成とエージェント設計 |
| [日本語 — ssos_eclss_loop](ja/scenario-ssos-eclss-loop.md) | SSOS 実 ECLSS シナリオ仕様 |
| [SSOS 接合（運用ガイド）](ja/ssos/index.md) | Docker + ROS 2 による ECLSS/EPS 接合手順 |
| [SSOS integration (operational)](en/ssos/index.md) | ECLSS/EPS integration via Docker + ROS 2 |
| [English — Overview](en/README.md) | Setup and project overview |
| [English — Architecture](en/architecture.md) | Layer design and agent flow |
| [English — ssos_eclss_loop](en/scenario-ssos-eclss-loop.md) | SSOS live ECLSS scenario spec |
| [エージェントガイド](ja/AGENTS.md) | コーディングエージェント向け規律 |

詳細は [catalog.md](catalog.md) を参照してください。
