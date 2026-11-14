# バランシングキューブを設定する

同梱入力は `src/scenario/balancing_cube/scenario.yaml` です。project `balancing-cube`、snapshot `cube.simulation.snapshot`、revision `bottom-corner-000-20261017-3` を選びます。このリビジョンがある既存の One Piece ストアを `--set ssot.path=/path/to/store` で指定します。パッケージはストアを同梱・復元しません。

## 必要な機能を導入する

準備済み Python 環境で実行します。

```bash
python -m pip install -e '.[mujoco,onepiece]'
```

`onepiece` extra は固定したリリース wheel を導入します。native CPU は MuJoCo extra、MJX は `gpu` extra と対応する CUDA 環境が必要です。GPU 環境は[開発者向け環境準備](../../../developers/setup.md)を参照してください。Isaac には別ランタイムと変換ツールが必要です。基本クイックスタートだけでは通常のキューブ実行に不足します。

## 設計モードとバックエンド

`--backend mujoco_cpu`（別名 `cpu`）が既定です。`--backend mjx_gpu`（別名 `gpu`）は CPU スクリーニングに加えて GPU 比較を要求します。必要な GPU 証拠が欠けても、GPU 検証済みとは扱いません。

`--design-mode none` は基準または明示的に適用した提案を評価します。既定の `llm` は予算を限定した提案生成を行います。`labeled_rule_base` は非対応です。同梱 LLM は Ollama、`llama3.2`、タイムアウト 30 秒、コンテキスト 32768 トークンです。既存サービスは [LLM 接続](../../guides/llm.md)で設定します。

探索の既定は 5 ラウンド、最大 20 候補、1800 秒、停滞 3 ラウンドです。CLI の上限は 20 ラウンド、80 候補、7200 秒、停滞 20 ラウンドです。`iteration.proposal_retries` は 0–3 を許可します。予算は CPU ケースの間と GPU バッチの前後で確認し、進行中の solver/JIT を中断しません。

## 凍結契約を守る

CLI の上書きルートは `ssot`・`backend`・`agents`・`iteration`・`output`・`memory` に限定します。memory は `enabled` と `seed_runs`、iteration は上記予算と `enabled` を受け付けます。ソース YAML の `workflow` 設定は通常 CLI で上書きできません。物理・閾値・乱数種の変更は承認済み SSOT リビジョンから行い、`--seed` は拒否します。

通常の設計提案が変えられるのは許可された設計フィールドだけです。制御器変更は別キャンペーンとなり、機械と制御器の同時変更には 2×2 比較が必要です。`--apply-proposals` は直接の提案、または `selected_candidate` を含む `design_proposals.json` を受け付けます。

出力はキューブの実験系統を使い、空または新規ディレクトリが必要です。変更しない証拠として扱います。[実行](running.md)と[結果](results.md)を参照してください。

## 許可する設計フィールド

次はコンパイラが許す外側の範囲です。選んだ SSOT スナップショットはさらに狭める場合があります。

| フィールド | 許容範囲 | 意味 |
| --- | --- | --- |
| `side_m` | 0.14–0.22 m | キューブ辺長 |
| `print_mass_ref_kg` | 0.08–0.25 kg | 寸法スケーリング前の印刷フレーム基準質量 |
| `wheel_mass_kg` | 0.035–0.09 kg | motor family の回転子質量を加える前の車輪質量 |
| `wheel_radius_ratio` | 0.23–0.40 | 車輪半径 / 辺長 |
| `inner_radius_ratio` | 0.65–0.92 | 車輪内半径 / 外半径 |
| `wheel_thickness_m` | 0.004–0.010 m | 車輪厚み |
| `tilt_q_scale`、`rate_q_scale`、`momentum_q_scale` | 0.25–4.0 | LQR の Q 群倍率。R は固定 |
| `yaw_rate_gain_nm_s` | 0–0.12 N·m·s | yaw 角速度の減衰ゲイン |

提案は登録済み motor family と 6 つすべての機械フィールド、または特殊な凍結基準を使います。任意の K、センサ仮定、時刻、判定閾値は変更できません。各値が範囲内でも、クリアランスや慣性の確認で失敗し得ます。

元の機械説明では、円環の軸方向慣性は質量と半径に依存し、厚みは横方向慣性に寄与することを区別しています。質量・半径を固定したまま厚みだけで軸方向慣性が増えたという説明は、コンパイルしたモデルで確認する必要があります。
