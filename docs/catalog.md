# ドキュメント索引

Engineering Agents のドキュメントは `docs/{言語}/` に集約されています。ルートの [README.md](../README.md) と [AGENTS.md](../AGENTS.md) は言語ハブです。

---

## ブラウザで閲覧

**MkDocs Material（推奨 — Mermaid・検索・ナビ付き）**

```bash
pip install -e ".[dev]"
mkdocs serve
# → http://127.0.0.1:8000/
```

静的 HTML:

```bash
mkdocs build
# 出力: site/ ディレクトリ
```

---

## 日本語（`docs/ja/`）

| ページ | 内容 |
| --- | --- |
| [概要](ja/README.md) | リポジトリ概要、セットアップ、ダッシュボード |
| [エージェントガイド](ja/AGENTS.md) | ミッション、レイヤ規律、コーディング規約 |
| [アーキテクチャ](ja/architecture.md) | レイヤ構成、実行フロー、エージェント設計 |
| [API 契約](ja/api-contracts.md) | `SimulatorProtocol`、JSONL スキーマ |
| [開発プラン](ja/development-plan.md) | 未完了機能、ロードマップ |
| [One Piece 連携](ja/one-piece-integration.md) | provenance エクスポート |
| [scrubber_degradation](ja/scenario-scrubber-degradation.md) | Mock 参照シナリオ仕様 |
| [ssos_eclss_loop](ja/scenario-ssos-eclss-loop.md) | SSOS 実 ECLSS シナリオ仕様 |

### SSOS 運用ガイド（`docs/ja/ssos/`）

| ページ | 内容 |
| --- | --- |
| [概要](ja/ssos/index.md) | Tier モデル、ファイル一覧 |
| [クイックスタート](ja/ssos/quickstart.md) | Docker 前提、2 ターミナル手順 |
| [ECLSS 統合](ja/ssos/eclss-integration.md) | Actions / Services / Topics |
| [EPS 統合](ja/ssos/eps-integration.md) | BCDU、`request_eps_boost` |
| [トラブルシューティング](ja/ssos/troubleshooting.md) | 型不一致、DDS、daemon |
| [API リファレンス](ja/ssos/api-reference.md) | `EclssBackend` / `EpsBackend` |

---

## English (`docs/en/`)

| Page | Content |
| --- | --- |
| [Overview](en/README.md) | Project intro, setup, dashboard |
| [Engineering guide](en/AGENTS.md) | Mission, layers, agent discipline |
| [Architecture](en/architecture.md) | Layer design and execution flow |
| [API contracts](en/api-contracts.md) | `SimulatorProtocol`, JSONL schemas |
| [Development plan](en/development-plan.md) | Roadmap and backlog |
| [One Piece integration](en/one-piece-integration.md) | Provenance export |
| [scrubber_degradation](en/scenario-scrubber-degradation.md) | Reference scenario spec |
| [ssos_eclss_loop](en/scenario-ssos-eclss-loop.md) | SSOS live ECLSS scenario spec |

### SSOS operational guides (`docs/en/ssos/`)

| Page | Content |
| --- | --- |
| [Overview](en/ssos/index.md) | Tier model, file index |
| [Quick start](en/ssos/quickstart.md) | Docker two-terminal workflow |
| [ECLSS integration](en/ssos/eclss-integration.md) | Actions / Services / Topics |
| [EPS integration](en/ssos/eps-integration.md) | BCDU, `request_eps_boost` |
| [Troubleshooting](en/ssos/troubleshooting.md) | Type mismatches, DDS, daemon |
| [API reference](en/ssos/api-reference.md) | `EclssBackend` / `EpsBackend` |

---

## 開発メモ（`docs/ja/memo/`）

| ファイル | 内容 |
| --- | --- |
| [バックログ](ja/memo/backlog.md) | BL-001〜BL-005 |
| [SSOS ECLSS 接合プラン](ja/memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) | Phase 0–7 実装・検証手順 |
| [SSOS EPS ROS2 接合プラン](ja/memo/ssos_eclss_loop/ssos_eps_ros2_connection_plan.md) | EPS ブリッジ（Phase 3） |
| [ROS2 グラフ設計調査](ja/memo/ssos_eclss_loop/ssos_ros2_graph_design_investigation.md) | launch remap 調査 |

---

## クイックリンク

```bash
pytest
./scripts/run_ssos_eclss_loop.sh
PYTHONPATH=src python3 -m scenario.ssos_eclss_loop.scenario_run --backend mock
```
