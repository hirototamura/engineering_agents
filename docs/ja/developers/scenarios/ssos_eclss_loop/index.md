# SSOS ECLSS ループを開発する

`ssos_eclss_loop` は貯蔵量の観測と生命維持操作を、実行中の操作担当と実行後の設計担当に分けて調整します。[スクラバー](../scrubber_degradation/index.md)、[キューブ](../balancing_cube/index.md)と並ぶ事例です。この分野のデータモデルは基盤全体の共通形式ではありません。

ライフサイクル、提案適用、エージェント・バックエンドの接続、失敗境界は[実装](implementation.md)、保存した得点、物理監査、完全性、候補選択は[評価](evaluation.md)を参照します。既存の設定とコマンドは[利用者ガイド](../../../users/scenarios/ssos_eclss_loop/index.md)にあります。

## 責務の対応

- `scenario_run.py`：解決済み入力、提案消費、バックエンド構築、操作・生存判定の順序、証拠、実行後の設計。
- `agent_config.py` と `scenario/agents`：操作・設計の独立モードとチーム・設計器。
- `design_tools.py`、`design_variables.py`、`design_constraints.py`、`design_proposals.py`、`design_eval.py`：サイジング、制約、候補実行、提案変換、選択。
- `evaluation.py`、`physics_gate.py`、`integrity_guard.py`、`unified_evaluation.py`：測定評価と受入可能性。
- `scenario/jobs/iterate.py`、`chain_memory.py`、`chain_selection.py`：適用設計の連鎖、小さな履歴、実行済み機械からの選択。
- `environment/ssos/eclss`：貯蔵・アクション境界、モック、プラント、ROS2 アダプタ、単位。

バックエンドは用途が異なります。ループモックは操作調整、プラントはモデルの物理とスコア、ROS2 は実 SSOS の操作です。プラントのスコアはモックと ROS2 には適用しません。グラフの接続変更とハードウェア容量変更も対応バックエンドが異なります。[利用者向け設定](../../../users/scenarios/ssos_eclss_loop/configuration.md)を参照してください。

設計提案と、承認され受入条件を満たして実行済みの最終設計は別の状態です。手動適用には状態・範囲の既知の制限が[実装](implementation.md)にあります。最終選択のラベルから、すべての経路に強制ゲートがあると判断しないでください。
