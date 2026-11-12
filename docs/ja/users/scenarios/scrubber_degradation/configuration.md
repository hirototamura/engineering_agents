# スクラバー劣化を設定する

同梱入力は `src/scenario/scrubber_degradation/scenario.yaml` と `agents.yaml` です。共通のマージ・出力規則は[設定リファレンス](../../reference/configuration.md)を参照してください。

## 初期条件と異常

既定は 50 ステップ、初期 CO₂ 800 ppm、電力余裕 150 W です。ステップ 20 から、スクラバー効率が毎ステップ 0.02、電力余裕が毎ステップ 3 W 減り、CO₂ 生成量は 1.4 倍になります。`anomalies` はリストなので、パッチはリスト全体を置換します。

`design_parameters` は生成・除去・電力・バイパス・負荷削減のモデル係数です。たとえば基礎スクラバー効率は 0.95、CO₂ 生成は 32 ppm/step、ファン電力は 80 W です。これらはモデル係数です。変更は実験条件の変更であり、ハードウェア設計が自動検証されたことにはなりません。

## エージェントのモード

`agents.mode` の既定は `none` です。`--agents-mode labeled_rule_base` は固定した回復方針を持つ 4 人のエンジニアを有効化します。`--agents-mode llm` は同梱の人物設定とモデル設定で、モデルに基づく議論と操作を行います。ラベル付きルールは思考スタイル archetype を使いませんが、構成は記録します。

チームのメモリ上限は 8 エントリ、会話窓は 12 メッセージです。LLM の既定は Ollama の `http://localhost:11434`、`gemma4:e4b`、温度 0.45、出力上限 512 トークンです。環境変数による上書きと前提サービスは [LLM 接続](../../guides/llm.md)を参照してください。

このシナリオは専用のステーションモデルを使い、ECLSS の mock・plant_sim・ros2 を切り替えません。`--apply-proposals` によるスクラバー再投入と `--iterate` には対応しません。固定の健全性・回復閾値は[結果](results.md)で定義します。

## 係数を変える前にトレードオフを知る

| 運用コマンド | モデル上の利点 | トレードオフ・限界 |
| --- | --- | --- |
| `set_fan_speed` | 流量増加で除去量が増える | ファン電力も増える |
| `enable_bypass` | 一時的な流量ボーナス | 電力負荷が増える。構造の辺は追加しない |
| `reduce_load` | CO₂ 生成量が減る | 詳細な乗員作業モデルでなく負荷削減の抽象化 |
| `request_eps_boost` | 一時的な電力支援 | 有限期間の mock EPS 応答 |

CO₂ 更新は小さな離散モデルであり、流体解析ではありません。

```text
production = configured_production × anomaly_multiplier × load_factor
removal = current_CO2 × efficiency × fan_speed × scrub_coefficient × bypass_factor
next_CO2 = max(400, current_CO2 + production − removal)
```

`load_factor` は負荷削減時以外 1、`bypass_factor` はバイパス有効時以外 1 です。この関係で、除去量を増やす操作が電力余裕を悪化させる理由を説明できます。モデル係数が実機の測定特性になるわけではありません。
