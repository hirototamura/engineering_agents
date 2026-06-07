# アーキテクチャ

## ミッション

設計変更を通じた ECLSS 異常検知のマルチエージェントシミュレーション（レジリエンス・ループ）。高忠実度の物理やグラフィックより、**構造化されたエージェント関係**と**シミュレータ API 契約**を優先する。

## 実装ステータス


| 機能                   | 状態        | 主要成果物                                                               |
| -------------------- | --------- | ------------------------------------------------------------------- |
| リポジトリ構成              | 完了        | `src/` レイヤ、`core/agents/`、`scenario/`                               |
| シミュレータプロトコル          | 完了        | `SimulatorProtocol`、`MockEclssSimulator`、`docs/api-contracts.md`    |
| ベースラインシナリオ           | 完了        | `scrubber_degradation/scenario.yaml`、`scenario/runner.py`、ベースラインテスト |
| Labeled エージェントチーム    | 完了        | ルールベース同種 N 体、`policy` 駆動、回復 + 事後設計提案                                |
| LLM モード              | 完了 / 調整中  | `agents.mode: llm` — 1 ラウンド議論 + 代表 action、policy 非参照                |
| One Piece provenance | 完了（Day5B） | `integrations/one_piece/client.py`、`provenance.jsonl`               |
| ダッシュボード              | 完了（Day6）  | `src/tools/dashboard/app.py`（トポロジグラフ含む）                             |
| CLI                  | 計画中       | `tools/cli.py`                                                      |


## 依存方向

import は一方向のみ:

```text
tools → scenario → environment → core
src/integrations/   （scenario/tools からのみ呼び出し）
```


| レイヤ                       | 責務                                                     |
| ------------------------- | ------------------------------------------------------ |
| `src/core/`               | Persona エージェント、Team/Scenario ABC、メモリ、LLM クライアント、イベントログ |
| `src/environment/`        | シミュレータ境界（`SimulatorProtocol`、SSOS モック/アダプタ、ECLSS ops）  |
| `src/scenario/`           | シナリオ YAML、runner、シナリオ固有エージェントチーム                       |
| `src/experiments/`        | 実行設定と結果（results は gitignore）                           |
| `src/tools/`              | CLI と Streamlit ダッシュボード                                |
| `integrations/one_piece/` | 設計変更 provenance の JSON SSOT                            |


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


| モード                 | 物理    | アクション                          | メッセージ                            | テスト                                   |
| ------------------- | ----- | ------------------------------ | -------------------------------- | ------------------------------------- |
| `none`              | モックのみ | —                              | —                                | `test_scrubber_baseline.py`（常に green） |
| `labeled_rule_base` | モック   | ルールベース同種 N 体（`policy`）         | `decision_source: rule`          | `test_scrubber_with_agents.py`        |
| `llm`               | モック   | LLM のみ（N+1 呼び出し/step、repeat 可） | `llm` / `llm_no_action` / `skip` | llm テスト                               |
| `base`              | —     | 未実装                            | BL-001 バックログ                     | —                                     |


チームは `scrubber_degradation` 専用の**同種エンジニア N 体**（`engineer_1` .. `engineer_N`）。進化ペルソナ研究は [memo/backlog.md](../memo/backlog.md) BL-002。

### Labeled（`policy` 専用）

`agents.yaml` の `policy` は `**labeled_rule_base` のみ**が参照。閾値は `co2_recovery_ppm` を中心に回復・事後 design ゲートを駆動する。


| 挙動        | ルールトリガー（要約）                                                  |
| --------- | ------------------------------------------------------------ |
| アラート / 診断 | CO2 ≥ `co2_recovery_ppm`；`anomaly_flags` あり                  |
| 回復コマンド    | 代表 `engineer_{(step-1)%N}` がファン・負荷削減・EPS・バイパス                |
| 事後設計提案    | peak CO2 ≥ `co2_recovery_ppm` または `anomaly_seen` → bypass 提案 |


### llm モード

- **1 ラウンド deliberation**（全 N 体）→ **代表 action**（`engineer_{(step-1)%N}`）→ 事後 design（最終 step の代表）
- **Situation**: `### Telemetry` + `### World state` のみ（`policy` 値は注入しない）
- 成功 → `decision_source: llm`；parse 失敗・空 commands → `message_type: skip`
- 実装プラン: [memo/homogeneous_agent_team_plan.md](../memo/homogeneous_agent_team_plan.md)

## 出力レイアウト

各実行は `src/experiments/results/<run_id>/` に書き込む:


| ファイル                   | タイミング                       |
| ---------------------- | --------------------------- |
| `telemetry.jsonl`      | 毎ステップ                       |
| `health_metrics.jsonl` | 毎ステップ                       |
| `design_state.jsonl`   | 毎ステップ（エージェント前トポロジ）          |
| `events.jsonl`         | 異常、回復コマンド、設計変更              |
| `messages.jsonl`       | `labeled_rule_base` / `llm` |
| `summary.json`         | 実行終了時に 1 回                  |


デフォルト run ID（`scenario.yaml`）:

- `scrubber_degradation_baseline` — `agents.mode: none`
- `scrubber_degradation_labeled_rule_base` — `labeled_rule_base`
- `scrubber_degradation_llm` — `llm`

スキーマ詳細: [api-contracts.md](api-contracts.md)。シナリオ叙事: [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md)。

## 外部システム


| システム      | MVP での扱い                                                             |
| --------- | -------------------------------------------------------------------- |
| SSOS      | モックアダプタ（`environment/ssos/mock_eclss.py`）；実 ROS2 は `SsosAdapter` スタブ |
| LLM       | Ollama（`core/llm/ollama.py`）；`llm` で使用                               |
| One Piece | JSON provenance（`integrations/one_piece/`、Day5B 実装済み）；Web UI は後回し    |
| EPS（電力）   | 完了（EPS-1〜4）: `StationSimulator`、SARJ/BCDU モック、`eps_telemetry.jsonl`  |


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
pytest tests/scenario/test_scrubber_with_agents.py -q  # labeled_rule_base 回復
```

