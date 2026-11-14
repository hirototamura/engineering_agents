# スクラバー劣化を開発する

`scrubber_degradation` は、モックのステーションで CO₂ 除去性能の劣化と電力余裕の低下に対応するチームを扱います。復旧操作、健全性分類、イベントの来歴、実行後の恒久設計提案を担当します。[SSOS](../ssos_eclss_loop/index.md)、[キューブ](../balancing_cube/index.md)と並ぶ同梱事例です。

シミュレータの結合、ステップチーム、操作処理、証拠を変える場合は[実装](implementation.md)、健全性の帯、復旧時刻、要約の意味を変える場合は[評価](evaluation.md)を参照します。既存の設定と実行は[利用者ガイド](../../../users/scenarios/scrubber_degradation/index.md)にあります。

## 責務の対応

- `scenario/scrubber_degradation/scenario_run.py`：実効設定、出力準備、ループ順序、要約、提案保存、来歴出力。
- `scenario/agents/scrubber_degradation_team.py`：議論、復旧案、シミュレータを通じた適用、実行後の設計提案。
- `environment/scrubber`：モック ECLSS、操作、設計状態、異常、EPS と結合するステーションの窓口。
- `environment/protocol.py`：スクラバー用のテレメトリ、健全性、コマンド、トポロジー、シミュレータの型。

設定でエージェントなし、ラベル付き規則、LLM のチームを扱います。EPS はモックまたは ROS 経由ですが、モックの ECLSS が SSOS に置き換わるわけではありません。明示的な契約変更なしで SSOS の貯蔵単位やスコアを持ち込まないでください。

## 現在の限界

チームが恒久変更を提案すると `design_proposals.json` を保存しますが、実行器は次回のシミュレーションへスクラバーの提案を適用しません。ダッシュボードの変更前後プレビューは再シミュレーションの証拠ではありません。ループを閉じるには、提案の明示的な検査・適用、消費した入力の保存、独立した 2 回目の実行、回帰確認が必要です。それまで実装済みと記述しないでください。
