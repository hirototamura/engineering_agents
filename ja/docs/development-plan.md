# 開発プラン（進行中・未着手）

本ドキュメントは **まだ完了していない機能** と **研究バックログ** を集約します。利用可能な機能の説明は [README.md](../README.md) および `ja/docs/` 配下の設計ドキュメントを参照してください。

---

## 現在のマイルストーン

### 完了（MVP として利用可能）

| 領域 | 内容 |
| --- | --- |
| SSOS モック | `StationSimulator`（ECLSS + EPS）、`SimulatorProtocol`、ROS2 風トピック定義 |
| シナリオ | `scrubber_degradation` — 50 step、step 20 から異常注入 |
| エージェント | `none` / `labeled_rule_base` / `llm`、同種エンジニア N 体（デフォルト 4） |
| 回復 | ファン加速、負荷削減、EPS ブースト、一時バイパス |
| 事後設計 | `design_proposals.json`（scrubber 凍結。ランタイムトポロジ変更なし） |
| provenance | `provenance.jsonl` — **ランタイム回復**（主に `request_eps_boost`） |
| ダッシュボード | Overview / Step replay / 2 run 比較 / 設計提案トポロジ可視化 |
| テスト | ベースライン・labeled・llm（モック LLM）の回帰 |

### 進行中

| 項目 | 説明 | 参照 |
| --- | --- | --- |
| LLM 比較実験 | モデル・温度・run_id を変えた軌道比較（ダッシュボード compare） | [architecture.md](architecture.md) |
| ドキュメント整備 | 本リポジトリの `ja/docs/` / `en/docs/` 更新 | — |

### 次の実装（優先順）

1. **ssos_eclss_loop** — SSOS ECLSS 段階接合（Phase 1a ARS smoke → 1b ARS+OGS → 2 +WRS → 3 EPS）— [memo/ssos_eclss_loop_connection_plan.md](../memo/ssos_eclss_loop_connection_plan.md)
2. **CLI 統合** — `python -m tools.cli run --scenario scrubber_degradation --agents-mode llm` などの単一エントリポイント（[memo/eps_implementation_plan.md](../memo/eps_implementation_plan.md) Day 8）
3. **provenance 拡張** — `design_proposals.json` を One Piece レコードへエクスポート
4. **provenance インデックス** — 複数 run 横断の `provenance_index.json`（ダッシュボード / CLI 比較用）
5. **SSOS 実機アダプタ** — `Ros2EclssBridge` + EPS ブリッジ（[memo/ssos_eps_ros2_connection_plan.md](../memo/ssos_eps_ros2_connection_plan.md)）

### その後（スコープ外に近い）

| 項目 | 状態 |
| --- | --- |
| One Piece Web / SSOT UI | 未接続（JSON provenance のみ） |
| 実 SSOS 軌道接続 | スタブのみ |
| `agents.mode: base` | 未実装（ラベルなし創発ロール）— [memo/backlog.md](../memo/backlog.md) BL-001 |
| 進化ペルソナ研究 | バックログ — BL-002 |

---

## ロードマップ（時系列）

```text
[完了]
  Day 1–2  レイヤ分離、SimulatorProtocol、telemetry
  Day 3–4  scrubber_degradation シナリオ、labeled チーム
  Day 5B   One Piece provenance（回復）
  Day 6    Streamlit ダッシュボード
  EPS-1–4  SARJ/BCDU モック、StationSimulator、eps_telemetry
  同種 N 体 LLM チーム（homogeneous agent team リファクタ）

[次]
  Day 8    CLI
  Day 9    provenance インデックス + design_proposals エクスポート
  Day 10   SSOS adapter 契約テスト

[研究]
  BL-001   base モード（創発ロール）
  BL-002   進化ペルソナ
```

詳細タスク分解: [memo/mvp_plan.md](../memo/mvp_plan.md)、EPS 区切り: [memo/eps_implementation_plan.md](../memo/eps_implementation_plan.md)。

---

## 研究メモ（`ja/memo/` / `en/memo/`）

実装プラン・ワークショップ文案・バックログ。リビングドキュメントではなく **設計プロセスの記録** です。

| メモ | 内容 |
| --- | --- |
| [mvp_plan.md](../memo/mvp_plan.md) | Week ロードマップ、Day 1–10 の振り返り |
| [homogeneous_agent_team_plan.md](../memo/homogeneous_agent_team_plan.md) | 同種 N 体 + 代表 action + post-run design の設計合意 |
| [persona_llm_core_oop_plan.md](../memo/persona_llm_core_oop_plan.md) | Persona / Team / LLM Core OOP（Day 1–8 完了記録） |
| [eps_implementation_plan.md](../memo/eps_implementation_plan.md) | EPS-1〜4、CLI・SSOS adapter の Day 区切り |
| [persona_workshop_draft.md](../memo/persona_workshop_draft.md) | Persona ワークショップ合意文案 |
| [backlog.md](../memo/backlog.md) | BL-001 創発ロール、BL-002 進化ペルソナ 等 |

---

## SSOS / One Piece 接合（開発途中）

```text
[ 本リポジトリ MVP ]
  MockEclssSimulator + EpsStack
       ↑ SimulatorProtocol
  ScrubberDegradationTeam
       ↓ JSONL + design_proposals.json
  Streamlit dashboard

[ 未接続 ]
  SSOS adapter (ROS2)     … スタブ・契約テスト予定
  One Piece Web UI      … provenance JSON のみ
  design_proposals → provenance … エクスポート未実装
```

One Piece 連携の現状: [one-piece-integration.md](one-piece-integration.md)。

---

## コントリビュータ向けチェックリスト

新機能を足すとき:

1. `SimulatorProtocol` または JSONL スキーマを変えたら [api-contracts.md](api-contracts.md) を更新
2. エージェントモードを増やしたら [architecture.md](architecture.md) とシナリオ doc を更新
3. 回帰: `pytest tests/scenario/test_scrubber_baseline.py`（常に）、`test_scrubber_with_agents.py`（エージェントあり）
4. 完了した項目は本ファイルの「完了」へ移し、README のロードマップを短く保つ
