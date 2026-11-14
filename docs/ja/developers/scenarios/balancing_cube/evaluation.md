# キューブの評価

[evaluation.py](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/balancing_cube/evaluation.py) は制約検査、目的関数の集計、CPU/GPU 一致を分離します。判定基準と試行計画の正本は固定した SSOT スナップショットです。公開する結果項目は[利用者向け結果ガイド](../../../users/scenarios/balancing_cube/results.md)を参照してください。

## 完全な数値証拠

`screening()` は対応する比較演算子で指標を検査し、宣言した期間のシミュレーション完了を要求します。数値の不等式は真偽値と非有限値を拒否します。`aggregate()` は期待する `(domain_id, condition_id, seed)` の一意な行列と完全一致することを要求し、空・非有限の証拠を拒否します。得点は制約合格率と固定した RMS・トルク代理量のペナルティから計算します。目的値の改善はゲートや試行条件の変更を許可しません。

集計の CPU 検証フラグはこの契約下で完了した数値証拠を示し、汎用の受入や実機の妥当性確認ではありません。GPU 検証は、さらにすべての対比較の合格を必要とします。

## 固定時間刻みの CPU/GPU 一致

`paired_metrics()` は軌跡の長さ、有限で増加する時刻、比較区間の充足、必要系列の有限性、欠測間隔を検査します。先頭区間の軌跡 RMSE とホイール最大値の差を許容差で確認し、終了状態・時刻と全エピソードの制約判定も比較します。

指標がゲートに近い場合は一致を不確定とします。現行比較は `half_step_adjudication_performed: false` を記録し、半分の時間刻みの追加判定を行わず、過去のその証拠を新しい結果として使いません。GPU 未実行や失敗を GPU 検証にしません。数値実装同士の一致はハードウェアへのモデル忠実度を示しません。

## 目的関数と数値の出典を分ける

集計は native CPU の要約から固定した目的関数を計算します。

```text
J = 制約合格試行数 / 全試行数
    − objective.rms_penalty × mean(final_1s_tilt_rms_deg)
    − objective.torque_proxy_penalty × mean(continuous_torque_exceeded_fraction)
```

技術的な重み付けであり、実機成功の確率ではありません。係数はスナップショットから取り、モデルは供給しません。レポートが保存した GPU 要約で同じ式を再計算しても、実行時の選択入力にはなりません。`adapter.py` は各試行に `evaluation_summary_source: native_cpu_reference` を記録し、`gpu_summary` を別に保存します。出典を明示せずに曲線を混ぜないでください。

| 証拠の状態 | 記録した意味 | 確立していないこと |
| --- | --- | --- |
| native 行列が完全 | CPU の制約・目的値がある | GPU 一致・実機忠実度 |
| GPU `not_run` | 理由付きの未実行 | CPU 代替は GPU 実行ではない |
| GPU `completed` | 高速実行の要約・軌跡がある | 対検査前の一致 |
| 対比較 `verified` | 全期間のゲートと先頭区間の許容差に合格 | 実機検証・半刻み判定 |
| 対比較 `inconclusive` | 区間不足・不正、ゲート付近、不一致 | 一致を検証済みとする許可 |
| 検証 `completed` | 選択した 1 候補の独立行列を実行 | 不合格でも自動受入すること |
| `selection_status: numerically_confirmed` | 検証完了、全制約合格、GPU 一致 | 実機基準の採用 |

CPU だけで数値開発の実行を完了し、選択が暫定のままという場合があります。一方、GPU を必須として未実行なら証拠が不完全です。すべての非エラーを同じ技術合格にせず区別します。

## 一致の計算とデータ範囲

許可した先頭区間で CPU 時刻に GPU の値を補間し、次を計算します。

```text
RMSE(x) = sqrt(mean((x_CPU(t_i) − interpolate(x_GPU, t_i))²))
```

傾斜 RMSE、角速度 3 軸の最大 RMSE、支点変位 RMSE、ホイール最大値の差を使います。時刻の区間充足と間隔、終了の一致、全期間の制約判定の一致も条件です。先頭区間の比較と全期間のゲートは異なる問いで、両方を記録します。[paired_metrics()](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/balancing_cube/evaluation.py)を参照してください。

## 失敗とテストの範囲

アダプタは期限・実行失敗を集計得点のない部分証拠として残します。ループは基準失敗、不完全な必須要因比較、固定コンテキストの変更、同期失敗を停止・不確定として記録します。完了した一部だけが良くても、部分評価の候補を選ばないでください。

現在の集計は物理的忠実度、電気エネルギー、温度予測を未確立とし、実機検証を偽とします。拡張にはモデルと証拠の契約を別に定める必要があります。

`tests/scenario/test_balancing_cube.py` で有限データ、完全行列、一致範囲、ゲート付近、GPU 不在、不完全証拠、要因比較の巻き戻し、最終配信失敗を確認します。追加シミュレータのテストと、制御した実行調整のテストを分け、確認結果には実際に動かした環境を示してください。
