# キューブの評価とキャンペーンを実行する

先に [SSOT ストアと依存](configuration.md)を準備します。毎回新しい実行 ID または保存先を使います。空でないキューブ実行先は `--force` を指定しても拒否されます。

## 凍結した設計を評価する

```bash
PYTHONPATH=src python -m tools.cli run balancing_cube \
  --design-mode none --backend mujoco_cpu \
  --set ssot.path=/path/to/onepiece-store \
  --run-id cube-reference-01 --dry-run --json
```

dry-run にもストアパスは必要ですが、ストアやシミュレータが実行可能かまでは確認しません。計画を見て `--dry-run --json` を外します。LLM へ提案を要求せず、凍結基準のスクリーニングと独立検証を行います。レビュー済み提案を評価するには新しい実行 ID と `--apply-proposals /path/to/design_proposals.json` を使います。

探索は接続可能なサービスと `--design-mode llm` を選び、たとえば `--iterate 3 --set iteration.max_candidates=8 --set iteration.max_wall_s=900` で予算を明示します。`--backend mjx_gpu` は準備済み GPU 環境で使います。選択候補と[検証状態](results.md)を確認してください。CPU 実行が完了しても、選択は暫定のままの場合があります。

## Isaac の証拠を準備する

Isaac は別の測定キャンペーンです。export は Engineering Agents 環境で、convert と audit は明示した Isaac Python で動きます。下の `GPU-REPLACE_WITH_ALLOCATED_UUID` は今回に割り当てられた GPU 1 台の UUID に置き換えます。convert には UUID 指定、pilot と batch には見える CUDA GPU がちょうど 1 台であることも必要です。batch は GPU の同一性も確認します。

```bash
PYTHONPATH=src python -m tools.cli isaac prepare export \
  --store /path/to/onepiece-store --output /path/to/new-isaac-input \
  --snapshot-revision bottom-corner-000-20261017-3
CUDA_VISIBLE_DEVICES=GPU-REPLACE_WITH_ALLOCATED_UUID PYTHONPATH=src python -m tools.cli isaac prepare convert /path/to/new-isaac-input \
  --python /path/to/isaac-python
PYTHONPATH=src python -m tools.cli isaac prepare audit /path/to/new-isaac-input \
  --python /path/to/isaac-python
```

export は `cube.xml` と `input.json`、変換と USD audit はそれぞれの記録を保存します。export の `--proposal` は直接の提案であり、`selected_candidate` のラッパーではありません。

pilot と batch は各コマンドに割当 UUID の `CUDA_VISIBLE_DEVICES=GPU-REPLACE_WITH_ALLOCATED_UUID` を付けます。

```bash
CUDA_VISIBLE_DEVICES=GPU-REPLACE_WITH_ALLOCATED_UUID PYTHONPATH=src python -m tools.cli isaac run pilot INPUT \
  --python ISAAC_PYTHON --output NEW_RUN
CUDA_VISIBLE_DEVICES=GPU-REPLACE_WITH_ALLOCATED_UUID PYTHONPATH=src python -m tools.cli isaac run batch INPUT \
  --python ISAAC_PYTHON --cases CASES_JSON --output NEW_RUN
```

pilot は接続確認です。batch は指定ケースを実行し、動画にはちょうど 8 ケースが必要です。`isaac run campaign INPUT --python ISAAC_PYTHON --output NEW_CAMPAIGN` は明示した Isaac ランタイムでキャンペーンを実行します。GPU shard ごとに 8 頂点を均等に含め、割当 GPU は 0–5 を許可します。期間、件数、乱数種、GPU、タイムアウトは各 `--help` を確認します。

## Isaac キャンペーンを確認する

`isaac analyze CAMPAIGN` は完全性と来歴の確認後に `statistics.json` と `screened-trials.json` を生成します。`isaac analyze CANDIDATE --reference REFERENCE --output NEW_COMPARISON_JSON` は同一の凍結試験計画を比較します。`isaac plot PATH` はテレメトリを表示します。`isaac propose CAMPAIGN --output NEW_DIR` は測定から制限付き機械提案を作りますが、提案自体は検証しません。

export・run・proposal の保存先はすべて新規にします。pilot、USD 設定値の audit、統計比較、実機で妥当性確認した設計を区別し、[結果](results.md)に従って解釈してください。

## 機械変更と制御変更を切り分ける

元の研究は、両方を変えた場合に 4 セル比較を保持します。

| | 凍結した制御器 | 提案した制御器 |
| --- | --- | --- |
| 凍結基準の機械 | `M0C0`: 比較基準 | `M0C1`: 制御の効果 |
| 提案した機械 | `M1C0`: 機械の効果 | `M1C1`: 同時変更 |

全セルで宣言条件を揃えます。基準は実行の凍結比較設計であり、直前の提案とは限りません。形状やゲインへ効果を帰属する前に各セルを比較します。同時変更の利得が、片側の悪化を隠す場合があります。

## 既存の Isaac 軌跡を解析する

元の campaign-analysis ツールは、対応する保存データを Isaac GPU ランタイムなしでも読みます。既存証拠を準備し、新しい出力先を使います。

```bash
PYTHONPATH=src python -m tools.isaac_analysis prepare \
  --campaign reference=/path/to/reference-campaign \
  --campaign candidate=/path/to/candidate-campaign --output /path/to/new-analysis-cache
PYTHONPATH=src python -m tools.isaac_analysis serve \
  --dataset /path/to/new-analysis-cache --port 8526
```

ビューアは `127.0.0.1` に bind します。フィルタは記録済みケースを選ぶもので、新しいゲイン・遅延・形状を試す機能ではありません。inventory・selection・quantiles・export は `PYTHONPATH=src python -m tools.isaac_analysis --help` で確認します。詳細な過去の `report` 本文は元の campaign プロトコルに固定され、非互換入力を拒否します。[分位帯と分母の規則](results.md#isaac-distributions)を読んでから比較してください。
