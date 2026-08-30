# ドキュメント索引

MkDocs サイトの全ページ一覧です。ヘッダーの言語切替で English を選べます。

| セクション | ページ | 内容 |
| --- | --- | --- |
| 開始 | [クイックスタート](index.md) | インストール、CLI、結果ファイル |
| | [概要](overview.md) | 目的、ダッシュボード、詳細セットアップ |
| 設計 | [アーキテクチャ](architecture.md) | レイヤ、実行フロー、エージェント |
| | [エージェント設計](agent-design.md) | 世界が強制すること／モデルが決めること、記憶3層、LLM 契約 |
| | [拡張ガイド](extending.md) | backend・シナリオ・エージェント・世界ルール・設計変数 |
| 実測 | [実験記録](results.md) | 50周の連鎖4本の実測 |
| | [ロードマップ](roadmap.md) | 優先順位と、その根拠になった実測 |
| 仕様書 | [実装仕様書](specs/index.md) | 各回の作り直しが対象にした仕様書（原文） |
| | [API 契約](api-contracts.md) | JSONL スキーマ、プロトコル |
| | [エージェントガイド](AGENTS.md) | ミッション、コーディング規律 |
| シナリオ | [scrubber_degradation](scenario-scrubber-degradation.md) | Mock CO₂ スクラバー |
| | [ssos_eclss_loop](scenario-ssos-eclss-loop.md) | SSOS 実 ECLSS |
| SSOS | [SSOS 接合](ssos/index.md) | Docker / ROS 2 運用ガイド |
| | [ロードマップ](ssos/roadmap.md) | Phase 0–8 状態 |
| その他 | [CLI ガイド](cli.md) | `ea` コマンド |
| | [設計ループの学術解析](design-loop-analysis.md) | 順序変数・臨界性・可制御性（キャンペーン HTML） |
| | [技術説明 ver.04](eclss_ai_agent_technical_report_04.md) | ハッカソン報告。第8章を創発の可視化に差し替え |
| | [技術説明 ver.03](eclss_ai_agent_technical_report_03.md) | ハッカソン報告＋定量解析（第11–14章） |
| | [開発プラン](development-plan.md) | ロードマップ索引 |
| | [保守ガイド](MAINTENANCE.md) | ドキュメント編集・プレビュー |
| メモ | [バックログ](memo/backlog.md) | BL-001–BL-007 |
| | [MVP プラン](memo/scrubber_degradation/mvp_plan.md) | Scrubber MVP |
| | [EPS 実装プラン](memo/scrubber_degradation/eps_implementation_plan.md) | EPS ブリッジ |
| | [同種エージェントチーム](memo/agents/homogeneous_agent_team_plan.md) | チーム設計 |
| | [SSOS ECLSS 接合プラン](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) | Phase 0–7 |
| | [乗員サバイバル](memo/ssos_eclss_loop/occupant_survival.md) | plant_sim の乗員・actor 減員 |
| | [ラベル付きルールベース](memo/ssos_eclss_loop/labeled_rule_base.md) | シミュレーション内 labeled 運用（必要量を積んでから上限） |
| | [事後設計エージェント](memo/ssos_eclss_loop/post_run_design_agent.md) | actor / designer 分離（実装済み） |
| | [設計エージェント](memo/ssos_eclss_loop/tool_use_design_agent.md) | 処理能力設計: 設計判断ループ / 改ざん検出 / 物理ゲート / 候補再シミュレーション |
| | [SSOS EPS ROS2 プラン](memo/ssos_eclss_loop/ssos_eps_ros2_connection_plan.md) | EPS（Phase 3） |
| | [ROS2 グラフ設計調査](memo/ssos_eclss_loop/ssos_ros2_graph_design_investigation.md) | launch remap |
| | [ECLSS 物理現象](memo/ssos_eclss_loop/ssos_eclss_physical_phenomena_overview.md) | ECLSS 物理メモ |
| | [EPS 物理現象](memo/ssos_eclss_loop/ssos_eps_physical_phenomena_overview.md) | EPS 物理メモ |
| | [CLI v3 プラン](memo/cli_v3_plan.md) | SSOS ホスト 1 コマンド |
| | [Persona LLM OOP](memo/agents/persona_llm_core_oop_plan.md) | Persona 設計草案 |
| | [Persona ワークショップ](memo/agents/persona_workshop_draft.md) | ワークショップメモ |

GitHub 入口: ルート [README.md](https://github.com/hirototamura/engineering_agents/blob/main/README.md) と [AGENTS.md](https://github.com/hirototamura/engineering_agents/blob/main/AGENTS.md)。

```bash
pip install -e ".[dev]"
mkdocs serve
# → http://127.0.0.1:8000/ja/
```
