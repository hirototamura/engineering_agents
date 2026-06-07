# One Piece 連携

最小 JSON SSOT レイヤによる設計変更 provenance。完全な [One Piece](https://github.com/hirototamura/one-piece) Web UI は現 MVP の**スコープ外**。

## 目的

実行中にエージェントが設計変更を提案・適用したとき、**誰が・いつ・何を・なぜ**変えたかを One Piece の provenance モデルと互換な形式で記録する。シミュレーションループはブロックしない。

## 想定レイアウト

```text
integrations/one_piece/
├── client.py          # 実行出力から provenance レコードを生成
└── ssot_schema.json   # MVP サブセット: elements, parameters, traces
```

## トリガー

`scenario/runner.py`（`ScrubberDegradationScenario`）は summary 書き込み後に provenance をエクスポート:

1. `events.jsonl` の設計変更行（`/eclss/events/design_change`）を読む
2. 対応する `messages.jsonl` と結合（`reasoning` / `decision_source`）
3. `design_state.jsonl` から変更前後のトポロジスナップショットを付与
4. 同一 run ディレクトリに `provenance.jsonl` を書く

各レコードは以下とリンク:

- `summary.json` の run ID と step
- `events.jsonl` の該当行
- 該当時は `messages.jsonl` のエージェントロール

## データモデル（MVP サブセット）

One Piece `SsotProvenanceRecord` 概念に準拠:

| フィールド | 例 |
| --- | --- |
| `actor` | `design_engineer`（rule）または将来の LLM エージェント ID |
| `actor_kind` | `ai_agent` / `logic_automation` |
| `step` | 35 |
| `change_kind` | `add_edge` |
| `payload` | manifold → scrubber の bypass エッジ |
| `before_topology` | 変更前 `design_state.jsonl` のスナップショット |
| `after_topology` | 変更後スナップショット |

保存: 実行出力と同じディレクトリの JSON（`provenance.jsonl`）。スキーマ契約は `integrations/one_piece/ssot_schema.json`。

## SSOS トポロジ取り込み（任意）

One Piece コネクタ [`one_piece_connectors/ssos.py`](https://github.com/hirototamura/one-piece/blob/main/packages/connectors/one_piece_connectors/ssos.py) は実 SSOS リポジトリから初期 `SystemElement` + ICD グラフをシードできる。MVP では `environment/eclss_ops/design_state.py` の Mock ECLSS デフォルトトポロジから `ssot_schema.json` を手書きしてもよい。

## 依存戦略

推奨（[mvp_plan.md](../memo/mvp_plan.md) も参照）:

- **JSON ファイル + 将来コネクタ** — provenance が安定するまで One Piece パッケージへのハード依存は避ける
- 取り込みが必要になったら git submodule または `pip install -e ../one-piece/packages/connectors`

## ステータス

**Day5B 完了（MVP スコープ）。**

- `integrations/one_piece/client.py` が `export_run_provenance(run_dir)` を提供
- `summary.json` に `provenance_path`、`provenance_record_count` を追加
- `labeled_rule_base` / `llm` 実行で設計変更 provenance を出力（該当時）

## Day5B 振り返り

- エクスポートは run 終了時だが、全 `design_change` ステップを記録（最終状態のみではない）
- ベースラインも `provenance.jsonl` を 0 件で出力し、ファイル契約を安定化
- trace に `reasoning`、`decision_source`、`parse_status` を載せられる

## 次の計画（Day5B 以降）

1. run インデックスエクスポート（`provenance_index.json`）— ダッシュボード/CLI の横断比較用
2. ~~回復コマンドの provenance 拡張~~ — **完了（EPS-4）**: `request_eps_boost` を `record_type: recovery` で記録
3. One Piece リポジトリがカスタムパースなしで取り込めるハンドオフ shim

## 関連ドキュメント

- [api-contracts.md](api-contracts.md) — `design_change` イベントスキーマ
- [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) — 実行出力での設計変更の見方
- [architecture.md](architecture.md) — `integrations/` のレイヤ配置
