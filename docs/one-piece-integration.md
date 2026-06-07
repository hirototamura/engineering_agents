# One Piece 連携

設計変更と運用回復の **provenance（来歴）** を、One Piece のデータモデルと互換な JSON で記録する。完全な [One Piece](https://github.com/hirototamura/one-piece) Web UI は現 MVP のスコープ外。

> JSONL スキーマ: [api-contracts.md](api-contracts.md)。未完了項目: [development-plan.md](development-plan.md)。

---

## 目的

自律ハードウェア開発の前段として、次を追跡可能にする:

1. **ランタイム回復** — 誰が、いつ、どの EPS ブーストを要求したか
2. **事後設計提案** — 誰が、なぜ、どのトポロジ変更を推奨したか（`design_proposals.json`）
3. （将来）One Piece SSOT への取り込みと横断インデックス

シミュレーションループは provenance 生成でブロックしない。失敗時は warning ログのみ。

---

## レイアウト

```text
src/integrations/one_piece/
├── __init__.py        # export_run_provenance
├── client.py          # events/messages からレコード構築
└── ssot_schema.json   # MVP サブセット（elements, parameters, traces）
```

---

## トリガーとフロー

`ScrubberDegradationScenario.run()` の末尾:

```text
1. team.propose_post_run_design()  → design_proposals.json
2. log.write_summary(summary)
3. export_run_provenance(run_dir)  → provenance.jsonl
4. summary に provenance_path / provenance_record_count を追記
```

```text
events.jsonl ──┐
messages.jsonl ├──► build_provenance_records() ──► provenance.jsonl
design_state.jsonl ┘
summary.json
```

---

## 現状エクスポートされるレコード

| 種別 | ソース | 現 scrubber_degradation |
| --- | --- | --- |
| `design_change` | ランタイム `/eclss/events/design_change` | **0 件**（ランタイムで設計適用しないため） |
| `recovery` | `request_eps_boost` の `recovery_applied` | **1 件以上**（labeled / llm で電力 critical 時） |

### 回復レコード（実装済み）

```json
{
  "record_id": "scrubber_degradation_labeled_rule_base:recovery:1",
  "record_type": "recovery",
  "run_id": "scrubber_degradation_labeled_rule_base",
  "scenario": "scrubber_degradation",
  "step": 28,
  "actor": "engineer_3",
  "actor_kind": "ai_agent",
  "change_kind": "request_eps_boost",
  "payload": {
    "support_w": 120.0,
    "eps": {"bcdu_mode": "discharging"}
  },
  "trace": {
    "event_kind": "/eclss/events/recovery_applied",
    "decision_source": "rule",
    "message": "Requesting EPS support boost of 120 W.",
    "reasoning": "Power margin critical; requesting temporary EPS assist."
  }
}
```

`actor` は `issued_by`（`engineer_*`）。`trace` は同一 step の `recovery_command` メッセージ（`from_role == actor`）から解決する。

### 設計変更レコード（プロトコル対応済み・データなし）

ランタイムで `apply_design_change` された場合の形式（将来または他シナリオ用）:

```json
{
  "record_id": "run_id:design_change:1",
  "run_id": "run_id",
  "scenario": "scrubber_degradation",
  "step": 35,
  "actor": "engineer_4",
  "actor_kind": "ai_agent",
  "change_kind": "add_edge",
  "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"},
  "before_topology": {"nodes": [], "edges": []},
  "after_topology": {"nodes": [], "edges": []},
  "trace": {
    "event_kind": "/eclss/events/design_change",
    "decision_source": "rule"
  }
}
```

---

## design_proposals.json との関係

| 成果物 | タイミング | provenance 連携 |
| --- | --- | --- |
| `design_proposals.json` | ラン終了後 | **未エクスポート**（開発予定） |
| `provenance.jsonl` | ラン終了後 | ランタイムイベントのみ |

事後の恒久提案（バイパス弁追加、非常電源、`set_parameter` 等）は `design_proposals.json` にあり、ダッシュボードが Before/After プレビューを描画する。One Piece へは **まだ自動連携しない**。

### 想定される次ステップ（Day 9）

1. `design_proposals.json` を読み、`record_type: design_proposal` レコードを追加
2. `before_topology` = `baseline_topology`、`after_topology` = 提案適用後の仮想グラフ
3. `trace.decision_source` = `rule` / `llm`、`trace.reasoning` = 提案理由

---

## データモデル（MVP サブセット）

One Piece `SsotProvenanceRecord` 概念に準拠。必須フィールド:

| フィールド | 説明 |
| --- | --- |
| `record_id` | `{run_id}:{種別}:{連番}` |
| `run_id` | 実行ディレクトリ名 |
| `scenario` | `scrubber_degradation` 等 |
| `step` | イベント step |
| `actor` | 代表エンジニア ID（`engineer_*`） |
| `actor_kind` | `ai_agent` / `logic_automation` |
| `change_kind` | `request_eps_boost`、`add_edge` 等 |
| `payload` | コマンド/変更の詳細 |
| `trace` | message、reasoning、decision_source、parse_status |

任意: `record_type`（`recovery`）、`before_topology` / `after_topology`（設計変更時）。

契約: `src/integrations/one_piece/ssot_schema.json`。

---

## summary.json とのリンク

```json
{
  "provenance_path": "src/experiments/results/scrubber_degradation_labeled_rule_base/provenance.jsonl",
  "provenance_record_count": 2,
  "design_proposals_path": ".../design_proposals.json",
  "design_proposal_count": 1
}
```

ベースライン（`agents.mode: none`）も **0 件の `provenance.jsonl`** を出力し、ファイル存在契約を安定化。

---

## SSOS トポロジ取り込み（任意・将来）

One Piece コネクタ [`one_piece_connectors/ssos.py`](https://github.com/hirototamura/one-piece/blob/main/packages/connectors/one_piece_connectors/ssos.py) は実 SSOS から初期 `SystemElement` + ICD グラフをシードできる。

MVP では `environment/eclss_ops/design_state.py` の Mock ECLSS デフォルトトポロジを使用。実 SSOS 接合は [development-plan.md](development-plan.md) の SSOS adapter を参照。

---

## 依存戦略

- **JSON ファイル + 将来コネクタ** — provenance 形式が安定するまで One Piece パッケージへのハード依存を避ける
- 取り込み必要時: git submodule または `pip install -e ../one-piece/packages/connectors`
- 方針詳細: [memo/mvp_plan.md](../memo/mvp_plan.md)

---

## ステータスまとめ

| 項目 | 状態 |
| --- | --- |
| `export_run_provenance()` | 完了 |
| EPS 回復 provenance | 完了 |
| ランタイム design_change provenance | プロトコルあり・現シナリオでは 0 件 |
| post-run `design_proposals` → provenance | **未実装** |
| `provenance_index.json`（横断） | **未実装** |
| One Piece Web UI | スコープ外 |

---

## 関連ドキュメント

- [api-contracts.md](api-contracts.md) — 全 JSONL スキーマ
- [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) — 出力の読み方
- [architecture.md](architecture.md) — 実行フロー
- [development-plan.md](development-plan.md) — Day 9–10 計画
