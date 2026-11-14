# CLI リファレンス

準備済みチェックアウトで `PYTHONPATH=src python -m tools.cli` を使います。このチェックアウトを指すインストール済み `ea` も同じアプリケーションです。各コマンドの `--help` が現在のオプションを示し、`--version` がパッケージバージョンを示します。

## コマンド

- `scenarios`: 同梱 3 シナリオの ID と説明を表示する。
- `run [scenario]`: シナリオを実行する。引数なしでは `scrubber_degradation`、シナリオを省略して `--iterate` を付けた場合は `ssos_eclss_loop`。
- `results [run_id]`: 最近の summary を一覧表示、または 1 件を表示する。`--track eclss|balancing_cube` で既定の実験系統を選び、`--limit` の既定は 10。
- `doctor`: Python、依存、Docker/SSOS、出力ルート、モデルサービスの接続性を報告する。シナリオ全体の検証ではない。
- `job run SPEC.json`: 保存した RunSpec を 1 回実行する。単一実行の仕様は、自動設計連鎖の制御全体を再生するものではない。
- `reports [build|serve|translate|capture|verify]`: ワークスペースのレポートライブラリを管理する。既定は `build`。[レポート](../guides/reports.md)を参照。
- `isaac prepare|run|analyze|plot|propose`: Isaac キューブ実験を準備・実行・確認する。[キューブの実行](../scenarios/balancing_cube/running.md)を参照。

## 実行制御

`--run-id`・`--output-dir`・`--results-root` は保存先を選びます。`--override-file` は YAML/JSON パッチを読み、繰り返せる `--set key=value` と専用フラグがそれを上書きします。`--dry-run` は計画を生成し、`--write-spec PATH` は dry-run でも実行入力を書きます。`--json` は機械可読出力、`--quiet` は通常出力を減らします。優先順位と保存先の規則は[設定](configuration.md)を参照してください。

ECLSS/スクラバーは必要に応じて `--steps`、エージェントモード、`--seed` を使います。ECLSS には独立した `--actor-mode`・`--design-mode`、`--backend`、`--inject-failures`、`--apply-proposals`、`--iterate 1..50`、対比較リプレイ、暫定承認の制御があります。正確な既定値と組合せは [ECLSS 設定](../scenarios/ssos_eclss_loop/configuration.md)が定義します。

`run balancing_cube` は別の backend・SSOT・反復・モード契約に分岐します。共通ヘルプは ECLSS を中心に記述されているため、適用前に[キューブ設定](../scenarios/balancing_cube/configuration.md)を確認してください。スクラバーには[専用のモード](../scenarios/scrubber_degradation/configuration.md)があり、提案の再投入はできません。

## 終了コード

`0` は実行完了、`1` は実行失敗、`2` は入力・設定エラー、`3` は環境エラーです。キューブでは inconclusive にも `2` を使います。終了コード 0 は工学的な制約の合格を意味しません。シナリオの評価を確認してください。

## 必要な成果物に合うコマンドを選ぶ

| 作業 | コマンド形式 | 主な出力 |
| --- | --- | --- |
| 単一実行の計画確認 | `run SCENARIO … --dry-run --json` | RunSpec 形式の入力。シミュレーションなし |
| 実行仕様の保存 | `run SCENARIO … --write-spec PATH` | 制御・上書きの JSON。全既定値ではない |
| その仕様を実行 | `job run PATH` | シナリオを 1 回実行 |
| 既定ルートの完了記録を読む | `results RUN_ID --track TRACK` | 既存の `summary.json` |
| レポートを探す | `reports build --workspace PATH` | 派生カタログ |
| Isaac 実験を準備・確認 | `isaac ACTION …` | 段階別のキューブ証拠 |

ECLSS 連鎖の通常 dry-run は回数と親ディレクトリを表示します。JSON/spec は子の RunSpec であり、連鎖全体の再生手順ではありません。連鎖コマンドとリポジトリの版も保持してください。
