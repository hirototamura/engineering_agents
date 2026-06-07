# ドキュメント索引

ECLSS レジリエンス・ループ・シミュレーション基盤のリビングドキュメント。

| ドキュメント | 対象読者 | 内容 |
| --- | --- | --- |
| [architecture.md](architecture.md) | コントリビュータ | レイヤ構成、依存方向、エージェントモード、実行フロー |
| [api-contracts.md](api-contracts.md) | インテグレータ | `SimulatorProtocol`、JSONL スキーマ、ROS2 風トピック |
| [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) | デモ・運用 | シナリオ叙事、ロール、出力の読み方 |
| [one-piece-integration.md](one-piece-integration.md) | 設計追跡 | One Piece provenance 実装と拡張計画 |

`docs/` 外の計画・研究メモ:

- [memo/mvp_plan.md](../memo/mvp_plan.md) — Week ロードマップとタスク
- [memo/persona_llm_core_oop_plan.md](../memo/persona_llm_core_oop_plan.md) — Persona LLM + Core OOP 実装プラン（Day 1–8 完了）
- [memo/persona_workshop_draft.md](../memo/persona_workshop_draft.md) — Persona ワークショップ合意文案
- [memo/eps_implementation_plan.md](../memo/eps_implementation_plan.md) — EPS-1〜4、Day 8–10
- [memo/backlog.md](../memo/backlog.md) — BL-001 ラベル付き vs 創発ロール 等

## クイックコマンド

```bash
pip install -e ".[dev]"
pytest

# 物理のみベースライン（agents.mode: none）
python src/scripts/run_mock_eclss.py

# ルールベース labeled チーム
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled'}})"

# Persona + 2ラウンド議論 + ガード付き LLM（Ollama 要）
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'llm'}})"

# ダッシュボード
python -m streamlit run src/tools/dashboard/app.py
```

## 現在のマイルストーン

- **完了**: ベースライン + labeled エージェント、同種 N 体 `llm` モード、One Piece provenance（設計変更 + EPS 回復）、ダッシュボード、`StationSimulator` / `mock_station`
- **次**: Day 8 CLI（[eps_implementation_plan.md](../memo/eps_implementation_plan.md)）→ provenance インデックス、SSOS アダプタ契約テスト

`from scenario.runner import ...` の前に `pip install -e ".[dev]"` が必要（パッケージは `src/` 配下）。
