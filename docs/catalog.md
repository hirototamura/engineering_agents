# ドキュメント索引

Engineering Agents リポジトリのドキュメント一覧です。

---

## SSOS ECLSS + EPS 接合（新）

`feat/ssos-eclss-loop` ブランチで実装された Space Station OS 接合の **エンドユーザー向け** ドキュメントです。

| ページ | 内容 |
| --- | --- |
| [概要](ssos/index.md) | アーキテクチャ、Tier モデル、ファイル一覧 |
| [クイックスタート](ssos/quickstart.md) | Docker 前提、2 ターミナル手順 |
| [ECLSS 統合](ssos/eclss-integration.md) | Actions / Services / Topics、smoke テスト |
| [EPS 統合](ssos/eps-integration.md) | BCDU、`request_eps_boost` interim |
| [ssos_eclss_loop シナリオ](ssos/scenario-eclss-loop.md) | mock / ros2 実行 |
| [トラブルシューティング](ssos/troubleshooting.md) | 型不一致、DDS、daemon |
| [ロードマップ](ssos/roadmap.md) | Phase 0–5 状態 |
| [API リファレンス](ssos/api-reference.md) | `EclssBackend` / `EpsBackend` |

### ブラウザで閲覧

**MkDocs Material（推奨 — Mermaid・検索・ナビ付き）**

```bash
pip install -e ".[dev]"
mkdocs serve
# → http://127.0.0.1:8000/ssos/
```

静的 HTML:

```bash
mkdocs build
# 出力: site/ ディレクトリ
```

**GitHub / GitLab**: `docs/ssos/index.md` を Web UI で開く（Mermaid 対応）。

---

## 既存ドキュメント

| ファイル | 内容 |
| --- | --- |
| [architecture.md](architecture.md) | レイヤ構成、実行フロー、エージェント設計 |
| [api-contracts.md](api-contracts.md) | `SimulatorProtocol`、JSONL スキーマ |
| [development-plan.md](development-plan.md) | 未完了機能、ロードマップ |
| [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) | 参照シナリオ仕様 |
| [one-piece-integration.md](one-piece-integration.md) | One Piece provenance 連携 |

---

## 開発メモ（内部向け）

| ファイル | 内容 |
| --- | --- |
| [memo/ssos_eclss_loop_connection_plan.md](../memo/ssos_eclss_loop_connection_plan.md) | ECLSS 接合実装プラン |
| [memo/ssos_eps_ros2_connection_plan.md](../memo/ssos_eps_ros2_connection_plan.md) | EPS ROS2 接合プラン |
| [AGENTS.md](../AGENTS.md) | コーディングエージェント向け規律 |

---

## クイックリンク

```bash
# テスト
pytest tests/environment/

# ECLSS smoke（SSOS Docker 起動後）
./scripts/run_ssos_eclss_smoke.sh
./scripts/run_ssos_eclss_1b_smoke.sh
./scripts/run_ssos_eclss_2_smoke.sh

# EPS smoke
./scripts/run_ssos_eps_smoke.sh

# ssos_eclss_loop（Mock）
PYTHONPATH=src python3 -m scenario.ssos_eclss_loop.scenario_run --backend mock
```
