# Engineering Agents — ECLSS レジリエンス・ループ

設計変更を通じた ECLSS 異常検知のマルチエージェントシミュレーション基盤。構成は [lunar_agents](https://github.com/sbilxxxx/lunar_agents) を参考にしている。

## リポジトリ構成

| パス | 用途 |
| --- | --- |
| `src/core/agents/` | Persona エージェント、Team/Scenario ABC、メモリ、LLM クライアント |
| `src/environment/` | シミュレータ API 境界（SSOS モック/アダプタ、ECLSS ops） |
| `src/scenario/` | シナリオ定義と runner（例: `scrubber_degradation`） |
| `src/experiments/` | 実行設定と結果 |
| `src/tools/` | CLI と Streamlit ダッシュボード |
| `integrations/one_piece/` | 設計変更 provenance（JSON SSOT） |
| `docs/` | [ドキュメント索引](docs/README.md) — アーキテクチャ、API 契約、シナリオ |
| `memo/` | 設計メモ（[mvp_plan.md](memo/mvp_plan.md)、[persona_llm_core_oop_plan.md](memo/persona_llm_core_oop_plan.md)） |

依存方向: `tools → scenario → environment → core`。詳細は [docs/architecture.md](docs/architecture.md) と [docs/scenario-scrubber-degradation.md](docs/scenario-scrubber-degradation.md)。

## クイックスタート

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest                    # または: python src/scripts/run_tests.py
```

### エージェントモード（`scrubber_degradation`）

| `agents.mode` | 説明 |
| --- | --- |
| `none` | 物理のみベースライン（エージェントなし） |
| `labeled` | ルールベース 4 ロール（Monitor / Diagnostician / Operator / DesignEngineer） |
| `labeled_llm` | Persona + 2 ラウンド議論（8 LLM 呼び出し/step）、ルール fallback なし |

Persona 定義は `src/scenario/scrubber_degradation/agents.yaml`（Day 8 ワークショップ確定）。**persona とシナリオは分離** — 閾値・テレメトリは実行時の `## Situation` に注入。

```bash
# 物理のみベースライン（agents.mode: none）
python src/scripts/run_mock_eclss.py

# ルールベース labeled チーム
python -c "from scenario.runner import run_scenario; print(run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled'}}))"

# Persona + 2ラウンド議論 + ガード付き LLM（Ollama 要、デフォルト qwen3.5:2b）
python -c "from scenario.runner import run_scenario; print(run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_llm'}}))"

# テスト
pytest tests/scenario/test_scrubber_baseline.py -q
pytest tests/scenario/test_scrubber_with_agents.py -q

# ダッシュボード
python -m streamlit run src/tools/dashboard/app.py
```

実行結果は `src/experiments/results/<run_id>/` に JSONL と `summary.json` を出力（baseline / labeled / labeled_llm）。スキーマは [docs/api-contracts.md](docs/api-contracts.md)。

## ライセンス

GNU General Public License v3.0

詳細は [LICENSE.txt](LICENSE.txt) を参照してください。
