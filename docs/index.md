# Engineering Agents — ドキュメント

ECLSS レジリエンス・ループと SSOS 接合のドキュメントへようこそ。

**→ [ドキュメント索引](catalog.md)** — 全ページ一覧

**→ [SSOS ECLSS + EPS 接合](ssos/index.md)** — `feat/ssos-eclss-loop` の運用ガイド

## クイックスタート

```bash
pip install -e ".[dev]"
mkdocs serve
# http://127.0.0.1:8000/
```

## 主要セクション

| セクション | 説明 |
| --- | --- |
| [SSOS 接合](ssos/index.md) | Docker + ROS 2 による ECLSS/EPS 接合 |
| [アーキテクチャ](architecture.md) | レイヤ構成とエージェント設計 |
| [API 契約](api-contracts.md) | JSONL / SimulatorProtocol |

詳細は [catalog.md](catalog.md) を参照してください。
