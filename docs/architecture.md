# アーキテクチャ

## ミッション

設計変更を通じた ECLSS 異常検知のマルチエージェントシミュレーション（レジリエンス・ループ）。高忠実度の物理やグラフィックより、**構造化されたエージェント関係**と**シミュレータ API 契約**を優先する。

## 実装ステータス

| 機能 | 状態 | 主要成果物 |
| --- | --- | --- |
| リポジトリ構成 | 完了 | `src/` レイヤ、`core/agents/`、`scenario/` |
| シミュレータプロトコル | 完了 | `SimulatorProtocol`、`MockEclssSimulator`、`docs/api-contracts.md` |
| ベースラインシナリオ | 完了 | `scrubber_degradation/scenario.yaml`、`scenario/runner.py`、ベースラインテスト |
| Labeled エージェントチーム | 完了 | ルールベース 4 ロール、`messages.jsonl`、回復 + 設計変更 |
| LLM guarded モード | 完了 / 調整中 | `agents.mode: labeled_llm_guarded` — Persona 議論 + ガード + rule fallback |
| One Piece provenance | 完了（Day5B） | `integrations/one_piece/client.py`、`provenance.jsonl` |
| ダッシュボード | 完了（Day6） | `src/tools/dashboard/app.py` |
| CLI | 計画中 | `tools/cli.py` |

## 依存方向

import は一方向のみ:

```text
tools → scenario → environment → core
src/integrations/   （scenario/tools からのみ呼び出し）
```

| レイヤ | 責務 |
| --- | --- |
| `src/core/` | Persona エージェント、Team/Scenario ABC、メモリ、LLM クライアント、イベントログ |
| `src/environment/` | シミュレータ境界（`SimulatorProtocol`、SSOS モック/アダプタ、ECLSS ops） |
| `src/scenario/` | シナリオ YAML、runner、シナリオ固有エージェントチーム |
| `src/experiments/` | 実行設定と結果（results は gitignore） |
| `src/tools/` | CLI と Streamlit ダッシュボード |
| `integrations/one_piece/` | 設計変更 provenance の JSON SSOT |

## 実行フロー（scrubber_degradation）

```text
scenario.yaml + agents.yaml
        │
        ▼
  scenario/runner.py → ScrubberDegradationScenario（レジストリ）
        │
        ├─ build_station_simulator() → StationSimulator（ECLSS + EPS）
        ├─ build_team() → ScrubberDegradationTeam（agents.mode ≠ none のとき）
        │
        ▼
  各ステップ:
    1. sim.step()                    → テレメトリ
    2. telemetry / health / design_state をログ（エージェント前スナップショット）
    3. team.run_step()               → messages, commands, design_changes
    4. team.apply_outcome()          → sim.apply_command / apply_design_change
    5. messages と新イベントをログ
        │
        ▼
  experiments/results/<run_id>/*.jsonl + summary.json
```

**タイミング注意**: ステップ *N* の `design_state.jsonl` は、そのステップの**エージェント行動前**のトポロジ。ステップ 35 で適用された設計変更は `events.jsonl` の step 35 に現れ、`design_state.jsonl` では step 36 以降に反映される。

## エージェントモード（`agents.mode`）

`scenario.yaml` で設定。`agents.mode` ≠ `none` のとき閾値は `agents.yaml`。

| モード | 物理 | アクション | メッセージ | テスト |
| --- | --- | --- | --- | --- |
| `none` | モックのみ | — | — | `test_scrubber_baseline.py`（常に green） |
| `labeled` | モック | ルールベース 4 ロール | `decision_source: rule` | `test_scrubber_with_agents.py` |
| `labeled_llm_guarded` | モック | LLM + ガード、失敗時 rule fallback | `llm` / `rule_fallback` | guarded モードテスト |
| `base` | — | 未実装 | BL-001 バックログ | — |

ロールは `scrubber_degradation` 専用の**シナリオ固有ラベル**（`ScrubberDegradationTeam`）。汎用ロールフレームワークではない。創発ロール研究は [memo/backlog.md](../memo/backlog.md) BL-001。

### Labeled ロール（`labeled` 主役 / LLM の rule fallback）

`labeled` では以下の閾値が行動タイミングを決める。`labeled_llm_guarded` では異常（step 20）以外のタイミングはエージェント判断。

| ロール | 責務 | ルールトリガー（要約） |
| --- | --- | --- |
| Monitor | アラート | CO2 ≥ 900 ppm |
| Diagnostician | 診断 | `anomaly_flags` あり |
| Operator | 回復コマンド | CO2 ≥ 1000 → ファン強化；電力 critical → 負荷削減；バイパス |
| DesignEngineer | 恒久設計変更 | step ≥ 35 かつ CO2 ≥ 1000 → bypass エッジ追加 |

### labeled_llm_guarded モード

- **2 ラウンド Persona 議論**: Round 1 オープンフォーラム（4 体）、Round 2 反応 + 行動（monitor/diagnostician は反応、operator/design は行動）
- **プロンプト層**: Team charter + `personas`（声・議論スタイルのみ）+ `## Situation`（シナリオ + テレメトリ）+ ディスコース + 個体メモリ + 出力契約
- **Persona とシナリオの分離**: 閾値・イベント・手段カタログは persona に書かない（[persona_workshop_draft.md](../memo/persona_workshop_draft.md)）
- parse + ガード成功 → `decision_source: llm`；失敗 → `rule_fallback` または設計の `llm_guard_reject`
- 実装プラン: [memo/persona_llm_core_oop_plan.md](../memo/persona_llm_core_oop_plan.md)

## 出力レイアウト

各実行は `src/experiments/results/<run_id>/` に書き込む:

| ファイル | タイミング |
| --- | --- |
| `telemetry.jsonl` | 毎ステップ |
| `health_metrics.jsonl` | 毎ステップ |
| `design_state.jsonl` | 毎ステップ（エージェント前トポロジ） |
| `events.jsonl` | 異常、回復コマンド、設計変更 |
| `messages.jsonl` | `labeled` / `labeled_llm_guarded` |
| `summary.json` | 実行終了時に 1 回 |

デフォルト run ID（`scenario.yaml`）:

- `scrubber_degradation_baseline` — `agents.mode: none`
- `scrubber_degradation_labeled` — `labeled`
- `scrubber_degradation_labeled_llm_guarded` — `labeled_llm_guarded`

スキーマ詳細: [api-contracts.md](api-contracts.md)。シナリオ叙事: [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md)。

## 外部システム

| システム | MVP での扱い |
| --- | --- |
| SSOS | モックアダプタ（`environment/ssos/mock_eclss.py`）；実 ROS2 は `SsosAdapter` スタブ |
| LLM | Ollama（`core/llm/ollama.py`）；`labeled_llm_guarded` で使用 |
| One Piece | JSON provenance（`integrations/one_piece/`、Day5B 実装済み）；Web UI は後回し |
| EPS（電力） | 完了（EPS-1〜4）: `StationSimulator`、SARJ/BCDU モック、`eps_telemetry.jsonl` |

provenance 計画: [one-piece-integration.md](one-piece-integration.md)

## 次の実装フォーカス

1. Day 8: CLI 統合と E2E エントリポイント（`run --scenario ... --agents-mode ...`）
2. Day 9–10: One Piece provenance インデックス、SSOS アダプタ契約テスト

## 開発セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

回帰ガード:

```bash
pytest tests/scenario/test_scrubber_baseline.py -q   # 物理のみ、常に
pytest tests/scenario/test_scrubber_with_agents.py -q  # labeled 回復
```
