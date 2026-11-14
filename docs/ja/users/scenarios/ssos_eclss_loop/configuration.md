# ECLSS ループを設定する

同梱入力は `src/scenario/ssos_eclss_loop/scenario.yaml` と `agents.yaml` です。マージと出力置換は[共通設定](../../reference/configuration.md)を参照してください。

## 実行に影響する既定値

引数なしの `run ssos_eclss_loop` は `plant_sim`、ラベル付き actor、LLM designer、対比較リプレイ付きの 50 回連鎖を選びます。小さなオフライン試験ではありません。ローカルで 1 回だけ実行するには backend と両モードを明示し、`--set iteration.enabled=false` を加えます。

actor/design のモードは `none`・`labeled_rule_base`・`llm` です。`--agents-mode` は actor モードの別名であり、`--actor-mode` と併用しません。actor を明示して design を省略すると、design は actor を継承します。反復可能な手順では両方を指定してください。LLM の provider/model フラグは LLM 担当だけに作用します。同梱設定は actor/designer に別々の研究室 vLLM を指定します。[LLM 接続](../../guides/llm.md)を参照してください。

## システムとバックエンド

既定は 50 ステップ、初期 CO₂ 1.3 kg、O₂ 8 kg、飲料水 80 L です。質量は kg で、ROS2 ブリッジが SSOS の g と変換します。水の体積は L です。

mock は `mock_dynamics` を使い、plant_sim と ros2 はその節を無視します。plant_sim の観測間隔は 1200 秒、乗員は 50 人です。actor が有効な場合、`plant_sim.crew.size` と `agents.actor.team.count` を一致させます。actor の操作上限は 1 ステップ 6 回です。ARS は既定で 4 ステップ（4800/1200 秒）占有し、その間の操作を拒否します。故障注入の既定は無効です。`--inject-failures` で設定済みの ARS/OGS/WRS の予定を有効化します。

ros2 には SSOS Docker/ROS2 とマウントが必要です。action/topic/startup の既定待機は 120/15/45 秒です。自動連鎖は mock と plant_sim に対応し、ros2 には対応しません。

## 設計変数と制約

容量設計で変えられるのは `plant_sim.ars.capacity_kg_day`（初期 4.5 kg/day）、`plant_sim.ogs.max_o2_kg_day`（9.25 kg/day）、`plant_sim.wrs.max_feed_l_per_operation`（10 L/operation）の 3 つです。追加容量を使えるように OGS/WRS の操作要求も上方向へ同期します。回収効率、乗員代謝、化学、検証閾値は容量設計変数ではありません。

目的は全員生存を優先し、その後に評価点を最大化します。`design_constraints` の範囲とソフト予算は、装置質量 4000 kg、総費用 500 MUSD、体積 14 m³ です。予算超過候補もシミュレーションでき、勝者に監督承認が必要な場合があります。範囲外候補は自動的な最終採用適格性を持ちませんが、暫定候補として返る場合があります。手動承認は範囲の強制保証ではありません。[採用の限界](../../guides/design-iterations.md)を確認してください。ラックのアフィン容量モデルと費用係数は探索用の仮定であり、実際の飛行機器の見積りではありません。

health と評価の意味は[結果](results.md)、反復と暫定採用は[設計の反復](../../guides/design-iterations.md)にあります。

## 装置容量と操作要求を分けて読む

| 対象 | フィールド例 | 意味 |
| --- | --- | --- |
| 設置容量 | `plant_sim.ogs.max_o2_kg_day` | モデル装置の定格処理能力 |
| 操作要求 | `agents.actor.policy.ogs_goal.input_water_mass` | 1 操作で要求する水量 |
| 観測時計 | `plant_sim.time.step_seconds` | 観測間で進む時間 |
| 操作時間 | `plant_sim.time.ars_operation_seconds` | 受理後に装置を占有する期間 |
| 検証の物差し | `thresholds.*`、`evaluation.*` | 結果を判断する条件 |

要求量を増やしても装置容量は増えず、容量を増やしても使う要求がなければ効果がありません。容量適用は関連する操作要求を同期し、評価要求は別に保持します。

ラック容量モデルは変更の負担も計算します。

```text
subsystem_quantity = fixed + variable_at_baseline × (capacity / baseline_capacity)
total_cost_musd = hardware_cost_musd + launch_cost_musd_per_kg × total_mass_kg
```

質量・体積・機器費用にはそれぞれの係数があります。容量増加は資源挙動を改善する一方、規模と予算の評価を悪化させ得ます。[結果](results.md)が生存と資源・規模の両方を含む理由です。
