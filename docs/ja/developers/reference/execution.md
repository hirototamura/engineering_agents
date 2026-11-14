# 内部の実行契約

現在の Python・ジョブの動作を説明します。公開オプションと既定値は[CLI リファレンス](../../users/reference/cli.md)を参照してください。

## 実行要求と結果

[RunSpec](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/jobs/spec.py) は `scenario`、任意の `overrides`、出力先の `output_dir`・`run_id`・`results_root`、`recreate_output`、`seed`、`apply_proposals_path`、`approve_provisional`、`design_history`、`force` を持ちます。直列化時に 3 つのパス項目を文字列へ変え、読み込み時に `Path` に戻します。データクラスの表現であり、版付きの外部シナリオ定義や網羅的な検証層ではありません。

`RunSpec` の `approve_provisional` の既定値は `False` です。CLI は異なる解決値を渡すことがあるため、対話コマンドからジョブの既定値を推定しないでください。`RunResult` は `run_dir`、`summary`、経過時間 `duration_s`、`exit_code`、任意の `error` を持ちます。

## 直列化する要求の例

内部データクラスの直列化を示す例です。外部シナリオの定義ではなく、この文書では実行しません。

```json
{
  "scenario": "scrubber_degradation",
  "overrides": {"simulation": {"steps": 3}, "agents": {"mode": "none"}},
  "output_dir": "/tmp/ea-contract-example",
  "run_id": null,
  "results_root": null,
  "recreate_output": false,
  "seed": null,
  "apply_proposals_path": null,
  "approve_provisional": false,
  "design_history": null,
  "force": false
}
```

| 項目群 | 直列化 | 実行時の責務 |
| --- | --- | --- |
| `scenario`、`overrides` | 文字列と JSON 互換の入れ子 | レジストリの受付とシナリオの検査 |
| `output_dir`、`results_root`、`apply_proposals_path` | 文字列化して `Path` に戻す | 対応する分岐が各パスを解釈 |
| `recreate_output`、`force` | 真偽値を保持 | 通常の出力解決。キューブは不変の出力を保つ |
| `seed` | 任意の数値を保持 | 実行器はシミュレーション設定を上書き。キューブは固定計画を使い拒否 |
| `approve_provisional`、`design_history` | 要求に保持 | 専用の分岐が扱い、汎用の採用保証ではない |

要求を保存して復元できることと、シナリオが項目に対応することは別です。`from_dict()` はデータクラスを作りますが、能力の交渉や全入れ子設定の検査は行いません。

## 振り分けと完了

`execute_run(spec, on_step=None, on_phase=None)` は固定レジストリの結合を使います。不明なシナリオはコード 2、シナリオ実行中の例外はコード 1 とエラー文字列を返します。SSOS とキューブには専用の分岐があり、汎用経路には `RunSpec` の全項目を渡しません。

実行後は `summary.json` が存在し、空でないオブジェクトとして読める必要があります。欠落、途中で切れた JSON、配列、空オブジェクトは、元ファイルを書き換えずコード 1 になります。キューブ以外の要約には経過時間と任意のシードを追加します。キューブの要約は同期対象の不変な成果物で、最終同期状態は返す結果へ別に加えられます。キューブの `status: inconclusive` はコード 2 です。実行コードがゼロでもエンジニアリング上の受入を示すわけではありません。

ROS2 のテレメトリ読み取り器は振り分け後の `finally` で後始末を試み、失敗を許容します。注入した故障の解除など、シナリオ固有の後始末はシナリオが担当します。

## 入口と限界

`python -m scenario.jobs SPEC.json` は直列化した要求を 1 つ受け、その実行コードを返します。Typer CLI は利用者・環境エラーも区別します（`tools/cli/exit_codes.py` の `0/1/2/3`）。これらの分類はシナリオ固有の結果状態を再定義しません。`run_scenario()` は実行を包み、非ゼロの結果で例外を出します。

`Scenario` は名前、設定の読み込み、シミュレータ・チームの構築、`run()` を定義します。実ランナーは引数を拡張し、キューブは継承していません。SSOS の連鎖反復は `ssos_eclss_loop` 専用で、キューブの反復は別の契約です。確認先は `tests/scenario/test_run_spec.py`、`test_iterate.py`、`test_balancing_cube.py`、`tests/tools/test_cli.py` です。
