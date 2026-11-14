# ローカルで設計を引き渡す

このチュートリアルでは `ssos_eclss_loop` のローカル `mock` バックエンドを使い、運用と実行後の設計をどちらもラベル付きルールで行います。Python 3.11 以上とリポジトリのチェックアウトが必要です。モデルサービス、Docker、ROS2 は不要です。mock で確認するのは提案の引き渡しであり、プラント容量や実機の安全性ではありません。

## チェックアウトを準備する

リポジトリのルートで実行します。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
PYTHONPATH=src python -m tools.cli scenarios
```

`scenarios` には `scrubber_degradation`、`ssos_eclss_loop`、`balancing_cube` が表示されます。追加依存は[シナリオごと](scenarios/index.md)に異なります。

## 1 回実行して提案を残す

未使用の実行 ID を選びます。既存の ECLSS 実行ディレクトリは既定で再作成されます。[出力先の規則](reference/configuration.md)を確認してください。

```bash
PYTHONPATH=src python -m tools.cli run ssos_eclss_loop \
  --backend mock --actor-mode labeled_rule_base \
  --design-mode labeled_rule_base --steps 20 \
  --run-id quickstart-run1 --set iteration.enabled=false --dry-run --json
```

計画が `mock`、両方のラベル付きモード、`iteration.enabled: false` を示すことを確認します。`--dry-run --json` を外すと実行できます。反復を明示的に無効化することで、設定済みの連鎖実行ではなく 1 回のシミュレーションになります。

出力先は `experiments/eclss/results/quickstart-run1/` です。`summary.json`、`telemetry.jsonl`、`design_proposals.json` を確認します。提案の `design_domain` は `ssos_graph`、`changes` は空でないことを確認してください。

## 提案をレビューして適用する

`design_proposals.json` の `changes`、`final_status`、`final_ineligible_reasons` を読みます。mock にはプラント検証がないため、ルール生成の提案には監督承認が必要です。次のコマンドはローカルの引き渡し確認として、未評価の提案を明示的に受け入れます。安全な実機設計の承認ではありません。

```bash
PYTHONPATH=src python -m tools.cli run ssos_eclss_loop \
  --backend mock --actor-mode labeled_rule_base \
  --design-mode labeled_rule_base --steps 5 \
  --run-id quickstart-run2 --set iteration.enabled=false \
  --approve-provisional \
  --apply-proposals experiments/eclss/results/quickstart-run1/design_proposals.json
PYTHONPATH=src python -m tools.cli results quickstart-run2
```

この承認フラグは手動適用時の提案状態ゲートを迂回し、制約適合を保証しません。一般的な意味と影響は[設計の反復](guides/design-iterations.md)を参照してください。

完了条件は、Run 1 が保持され、Run 2 に `consumed_proposals.json` があり、保存設定に変更が反映されていることです。短い 2 回目の実行は適用確認用です。条件の異なるテレメトリから改善を主張しないでください。次は [ECLSS の実行](scenarios/ssos_eclss_loop/running.md)でプラントによる比較を行い、[結果の確認](guides/inspect-results.md)で証拠を判断します。

## ディスク上の引き渡しを確認する

両コマンドが完了したら、ある実行が「出した提案」と次回が「消費した入力」を区別します。

```text
experiments/eclss/results/
├── quickstart-run1/
│   ├── scenario_config.yaml
│   ├── summary.json
│   ├── telemetry.jsonl
│   └── design_proposals.json       → proposed next change
└── quickstart-run2/
    ├── scenario_config.yaml        → effective applied configuration
    ├── consumed_proposals.json     → preserved handoff input
    ├── summary.json
    └── telemetry.jsonl             → new observations
```

ほかの評価・エージェント記録も存在します。Run 2 では、そこで新たに生成した提案を読む前に、`consumed_proposals.json` と Run 1 の提案を照合します。Run 2 が出した提案は、さらに後の実行に向けたものです。
