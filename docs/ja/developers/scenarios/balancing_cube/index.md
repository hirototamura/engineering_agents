# バランシングキューブを開発する

`balancing_cube` は、版付き One Piece 入力と決定論的な数値証拠に基づいて、リアクションホイール式キューブの機械・制御を提案します。[スクラバー](../scrubber_degradation/index.md)、[SSOS](../ssos_eclss_loop/index.md)と並ぶ事例です。

SSOT 解決、コンパイル、設計反復、ワークフロー、記憶、同期を変える場合は[実装](implementation.md)、制約検査、集計、数値的一致を変える場合は[評価](evaluation.md)を参照します。公開の前提、コマンド、結果の読み方は[利用者ガイド](../../../users/scenarios/balancing_cube/index.md)にあります。

## 責務の対応

- `scenario_run.py`：設定、必須の SSOT 出典、バックエンドとモードの選択、設計ループ構築。
- `design.py`：範囲付きの機械・制御コンパイル、従属量、入力ダイジェスト、試行行列。
- `adapter.py`：固定スナップショットとリセット、実行調整、決定論的フィードバック、不完全証拠の保持。
- `loop.py`：基準評価、提案反復、上限、要因比較、選択、公開。
- `workflow.py` と `memory.py`：専門家間の受け渡し、上限付きのプロンプト、証拠付きエピソード。
- `environment/mujoco`：ネイティブと MJX の実行、モデル、接触、制御。
- `integrations/one_piece/mechanical_bridge.py`：厳密な入力の版、コンテキスト投影、永続的な配信。

通常のシナリオはネイティブ MuJoCo CPU と MJX GPU を使います。`isaac_*` と `environment/isaac` は別経路の変換、キャンペーン、分析を支援し、Isaac は通常ランナーの受付バックエンドではありません。数値開発の証拠と過去キャンペーンの主張を区別してください。

正本のスナップショットが必要で、ミッション、モデル、要件、計画をローカル既定値へ代替しません。現行の数値ループは、実機の妥当性、電気エネルギー、温度予測を確立しません。
