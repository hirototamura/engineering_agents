# 設定リファレンス

各同梱シナリオには `src/scenario/<scenario>/scenario.yaml` があります。ECLSS とスクラバーには `agents.yaml` もあり、scenario 内の `agents` セクションが上書きします。これは実装済みシナリオの入力であり、任意の外部シナリオパッケージを CLI で読み込む仕組みではありません。

## マージと値の規則

ECLSS/スクラバーの優先順位は、同梱設定、`--override-file`、繰り返しの `--set`、`--steps` や `--actor-mode` などの専用オプションの順に高くなります。マッピングは再帰的にマージし、リストを含む他の値は置換します。`--set` は真偽値、null、整数、小数を解釈します。構造を持つリストには YAML/JSON パッチを使います。未知の `--set` パスはマージした scenario/agents のキーに対して拒否されます。ただし反復既定値には限定的な例外があります。

環境設定は別に解決します。`SSOS_ECLSS_BACKEND` は未選択の ECLSS バックエンドを補い、LLM 環境変数は接続設定を上書きできます。[LLM 接続](../guides/llm.md)に詳細があります。明示した ECLSS バックエンド設定が環境の既定より優先されます。キューブには別の[制限付き上書き検証](../scenarios/balancing_cube/configuration.md)があります。

`--write-spec` は RunSpec の制御と上書きパッチを保存します。同梱の全既定値を凍結したものではありません。完了した ECLSS/スクラバー実行は `scenario_config.yaml` と、エージェント設定があれば `agents_config.yaml` を保存します。キューブは独自の契約で SSOT 入力と証拠を保存します。

## 出力先ディレクトリ { #output-directories }

ECLSS/スクラバーは `experiments/eclss/results/<run_id>/`、キューブは `experiments/balancing_cube/results/<run_id>/` を使います。`EA_RESULTS_ROOT` は両方の既定ルートを上書きします。`--output-dir` はルートと実行 ID より優先されます。それ以外では `--results-root` が環境・既定ルートより優先されます。実行 ID は英数字で始め、英数字・`.`・`_`・`-` を使えます。パス区切りと `..` は拒否します。

ホストからの ECLSS `ros2` 実行は例外です。`--output-dir` は拒否し、リポジトリの `experiments/eclss/results` を `/ea/results` へマウントする必要があります。独自ルートや `EA_RESULTS_ROOT` も同じマウント先を指す必要があります。新しい `--run-id` を選び、[ROS2 準備](../scenarios/ssos_eclss_loop/running.md)を参照してください。

ECLSS/スクラバーは既存の実行・連鎖ディレクトリを既定で再作成し、旧成果物を削除します。実行と認識できない内容は `--force` がなければ保護されます。単一実行の `--no-recreate` は最初の削除を避けますが、再開機能ではなく、設定・summary の上書きとストリーム追記が起こり得ます。ECLSS 連鎖では親だけを保持し、連鎖メモリを消去して番号付き子実行と対比較リプレイを再作成します。このフラグがあっても同じ連鎖 ID の再利用で証拠を置換し得ます。過去の連鎖を保持するには新しい実行 ID または親ディレクトリを使ってください。

キューブは過去の証拠を保持し、空でない保存先を拒否します。再作成の既定値や `--force` も置換を許可しません。[実行手順](../scenarios/balancing_cube/running.md)を参照してください。

## シナリオごとの値

単位、既定値、許可する設計変数、前提サービスは[スクラバー設定](../scenarios/scrubber_degradation/configuration.md)、[ECLSS 設定](../scenarios/ssos_eclss_loop/configuration.md)、[キューブ設定](../scenarios/balancing_cube/configuration.md)を参照してください。同じような設定名でも、同じ物理を表すとは限りません。

## マージの具体例

上書きファイルが `simulation.steps: 20`、コマンドが `--set simulation.steps=30` と `--steps 40` を指定する場合を考えます。

| 適用した層 | その層の後の値 |
| --- | ---: |
| 上書きファイル | 20 |
| `--set simulation.steps=30` | 30 |
| `--steps 40` | 40 |

実行には 40 ステップを使います。これは優先順位の例であり、推奨観測期間ではありません。リストはマッピングと異なり、`anomalies` を変更するとリスト全体を置換します。ネストしたマッピングの 1 キーだけの変更なら他のキーを保持します。保存した実効設定で確かめてください。
