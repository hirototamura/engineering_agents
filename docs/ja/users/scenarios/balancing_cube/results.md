# キューブの証拠を解釈する

`summary.json` から始めます。実行状態、選択候補、停止理由、スクリーニング・独立検証、GPU 状態、公開状態は別々の項目です。正常終了だけで物理設計を昇格させることはできません。

## スクリーニング・選択・独立検証

提案生成の前に基準をシミュレーションします。各候補は凍結した探索行列の全ケースを使います。探索で選んだ最良設計を、別の凍結検証行列で確認します。基準と必要時間は SSOT 契約から得ます。

探索の目的関数は次です。

```text
screening_pass_fraction
− rms_penalty × mean(final_1s_tilt_rms_deg)
− torque_proxy_penalty × mean(continuous_torque_exceeded_fraction)
```

係数は `plan.objective` から得ます。トルク項は代理指標であり、電気エネルギーや熱の予測ではありません。合計指標に加え、ケースの結果と制約を確認します。

GPU を要求した場合も、スクリーニングの正本は CPU です。GPU 検証は固定時間刻み、許容誤差、期間・状態の一致、判定境界付近の除外のもとで、全区間の gate 結果と軌跡の先頭区間を比較します。半分の時間刻みによる裁定は行いません。

CPU のみでも `status: completed` になれますが、選択は `provisional` に留まります。`numerically_confirmed` には独立検証の完了、全スクリーニング合格、GPU 一致の合格が必要です。GPU 欠如は `not_run` であり、CPU 証拠で代用しません。`physical_verified` は false、`physical_fidelity`、電気エネルギー、温度予測は null です。数値一致はモデル忠実度や実機適合を立証しません。

## 保持する記録

`frozen-snapshot.json`、`environment.json`、`policy-initial.json` は入力です。`candidates/candidate-NNN/compiled.json` と `result.json` は評価候補を残します。`round-NN/` は完了段階に応じて SSOT context、prompt/proposal、policy を保存し、failed/rejected/pending 記録は未完了の証拠を保持します。`validation/` は独立検証の設計と結果です。

`design_proposals.json` は選択証拠と引き渡し案です。`onepiece-outbox.json`、`sync-status.json`、`publication/summary.json` はローカル証拠と One Piece への配送を分けます。公開待ちで次の提案作業が止まっても、ローカル記録と永続 outbox は残ります。任意の `memory/episodes.jsonl` は設計助言の文脈であり、検証の権限ではありません。

## Isaac の証拠の限界

`conversion.json` と `usd-audit.json` は変換と USD 設定値の記録であり、接触 solver の同等性を示しません。pilot は理想的な sensing のもとでの接続確認であり、完全な遅延・ノイズモデルを実装しません。campaign 解析は未完了・改変された計画、来歴不一致、重複、欠損ケースを拒否します。

Wilson 区間は乱数種で定めた初期条件分布での成功を表します。対比較は記述的で、p 値は多重性未調整です。選択の主張には新しい検証乱数種が必要です。レポートはバックエンド間一致、モデル忠実度、実機の不確かさを立証しません。`isaac propose` の出力は、新しい測定キャンペーンを要する仮説です。

## 集約値の前に指標を読む

| 量 | 作り方 | 解釈の限界 |
| --- | --- | --- |
| `final_1s_tilt_rms_deg` | 終了前 1 秒の総傾斜の二乗平均平方根 | 早期失敗にも最後の窓がある。独立した期間 gate が必要 |
| `contact_fraction` | 初回を除く観測で、法線力がモデル境界を超える割合 | サンプル化したモデル指標で、実機信頼度ではない |
| `continuous_torque_exceeded_fraction` | どれか 1 車輪でも比較閾値を超える物理ステップの割合 | 3 車輪で平均しない。温度予測ではない |
| `speed_governor_fraction` | 同方向への追加加速を governor が阻止した物理ステップの割合 | 最大速度だけとは異なる |
| `screening_pass_fraction` | 全凍結 gate を満たしたケース / 全宣言ケース | 選んだ試験分布に依存する |

元の解説の RMS 定義は次です。

```text
e_RMS = sqrt((1/N) × Σ(theta_i²))
```

`theta_i` は総傾斜であり、2 軸の誤差の別々の平均ではありません。サンプル観測と物理ステップのカウンタは分母が異なります。レポートの計算を再現するときは保存時刻とカウンタ定義を使います。

### 過去の点数計算例 — 2026 年 10 月

10 月 20 日のコード・証拠解説は、10 月 17 日の上側車輪研究の **GPU 並列結果を使った投影値**を記録しています。

```text
J = k/12 − 0.05 × mean(e_RMS) − 0.2 × mean(f_tau)
J = 12/12 − 0.05(0.1699230270) − 0.2(0) = 0.9915038486
```

これは元の式と記録値であり、新しい評価ではありません。係数と 12 ケースの分母は、その凍結研究に属します。新規実行は自身の `plan.objective` と行列を読みます。

| 過去の記録 | 実装・条件 | 記録点数 |
| --- | --- | ---: |
| 上側車輪の保持した研究設計 | Native MuJoCo。実行時の選択正本 | 0.9916124707 |
| 同じ研究設計の後のレポート投影 | 保存 MJX summary、12 ケース合格 | 0.9915038486 |
| 新規 GPU audit | 別の audit 条件 | 0.9914858776 |
| 下側車輪の初回試験 | Native 探索、12 ケース合格 | 0.9885861309 |

各行を 1 本の進歩曲線につながないでください。実装や条件が異なり、元の監査では下側 12 ケース全体の GPU 点数は未測定でした。約 0.99 は実機成功率 99% ではありません。元の単一指標は、合格 1 ケースに `1/12 = 0.083333`、平均 RMS 0.1° 減少に `0.005`、トルク超過率 1 パーセントポイント減少に `0.002` を与えます。これは数値上の方針であり、物理法則ではありません。

元の初回試験では、既知の特定失敗が改善する一方、集約点数は下がりました。ケース表と目的関数の両方を読む理由です。出典は英語の[10 月 20 日の解説](https://github.com/hirototamura/engineering_agents/blob/648237d8596462362b5772914242a3881f82ad35/docs/en/balancing_cube_simulation_walkthrough.md)、[下側取付けの初回試験](https://github.com/hirototamura/engineering_agents/blob/648237d8596462362b5772914242a3881f82ad35/docs/en/bottom_corner_trial.md)、[ワークフロー研究](https://github.com/hirototamura/engineering_agents/blob/648237d8596462362b5772914242a3881f82ad35/docs/en/balancing_cube_workflow_study.md)です。元の実験範囲を保持した資料であり、実機ベースラインの採用ではありません。

## 分母とともに Isaac の分布を読む { #isaac-distributions }

元の 10 月 24 日の campaign 解析は、各時刻の中央値と中央 **68.3%・95.5%・99.7%・100% の経験的被覆帯**を保持します。時刻ごとの状態分布であり、平均の信頼区間や正規分布の仮定ではありません。異なる機械構成は別々に描きます。

| 解析モード | 記録された評価停止後のサンプル | 後半の帯の意味 |
| --- | --- | --- |
| `all-recorded` | 制御停止後の自由運動も全記録を含める | 転倒を含む、選択ケースの観測結果 |
| `evaluation-only` | 各ケースは停止サンプルまで含める | 評価中であることを条件とした分布。件数が減り得る |

過去の基準 corner 001 の 3 秒時点では、上側 97.75 percentile が全記録で約 **57.245°**、evaluation-only で **0.176°** でした。制御器が 2 通りに改善したのではなく、分母が変わった例です。

時刻ごとの `count`、`evaluation_count`、選択 ID、outcome フィルタ、停止後方針を残してください。停止後の欠損は補完しません。記録した tilt は幾何学的な真値で、ノイズ付き制御入力ではありません。過去 pack の停止後 motor チャンネルには、実際の送信 effort が 0 でも仮計算の要求が残る場合があり、tilt だけでは全動画を復元できません。

英語の[元の campaign 解析手順](https://github.com/hirototamura/engineering_agents/blob/648237d8596462362b5772914242a3881f82ad35/docs/en/isaac-campaign-analysis.md)に、24,576 ケース × 2 campaign と証拠の限界があります。[既存データの読解手順](running.md)で対応する保存 campaign を確認します。この解析は物理の実行、ゲイン調整、gate 変更を行いません。
