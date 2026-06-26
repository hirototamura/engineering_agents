# アーキテクチャ — ECLSS レジリエンス・ループ

レイヤ構成・実行フロー・エージェント設計のリファレンス。API スキーマは [api-contracts.md](api-contracts.md)、叙事は各シナリオドキュメントを参照。

> 利用手順: [README.md](../README.md) · 未完了: [development-plan.md](development-plan.md)

---

## ミッション

宇宙ステーションの **生命維持装置（ECLSS）** における異常・運用負荷に対し、**エージェントチームが検知・対応し、事後に設計変更を提案する**までを再現可能な環境で検証する。

優先するもの:

- **構造化されたエージェント関係**（同種チーム、代表 action、議論ログ）
- **明確な API 契約**（バックエンドプロトコル、JSONL）
- **二系統のシナリオ** — 独立したバックエンドと出力スキーマ（混在しない）


|        | `scrubber_degradation`                                               | `ssos_eclss_loop`                                          |
| ------ | -------------------------------------------------------------------- | ---------------------------------------------------------- |
| 叙事     | [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) | [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md) |
| バックエンド | `SimulatorProtocol` / `StationSimulator`                             | `EclssBackend` / `Ros2EclssBridge`                         |
| チーム    | `ScrubberDegradationTeam`                                            | `SsosEclssLoopTeam`                                        |
| 代表 ID  | `engineer_`*                                                         | `eclss_operator_*`                                         |
| ランタイム  | 回復コマンド                                                               | 運用コマンド（ARS/OGS 等）                                          |
| 事後提案   | scrubber トポロジ                                                        | `ssos_graph`                                               |
| 実行環境   | ホスト Python のみ                                                        | mock または SSOS Docker                                       |


---

## 共通 — レイヤと依存

### システム全体像

```text
┌─────────────────────────────────────────────────────────────┐
│  tools/          Streamlit dashboard, ea-loop (Docker)      │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  scenario/       scrubber_degradation  |  ssos_eclss_loop   │
│                  ScrubberDegradationTeam | SsosEclssLoopTeam│
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
    ┌───────────▼──────────┐      ┌───────────▼──────────────┐
    │ environment/         │      │ environment/ssos/        │
    │ StationSimulator     │      │ EclssBackend             │
    │ MockEclss + EPS mock │      │ Ros2EclssBridge          │
    └───────────┬──────────┘      └───────────┬──────────────┘
                │                             │
                └─────────────┬───────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│  core/           PersonaAgent, Team ABC, memory, Ollama     │
└─────────────────────────────────────────────────────────────┘

  integrations/one_piece/  ← scenario 終了時に provenance エクスポート
```

**依存方向**（import は一方向のみ）:

```text
tools → scenario → environment → core
src/integrations/   （scenario から呼び出し）
```

### レイヤ責務


| レイヤ          | パス                            | 責務                                                                         |
| ------------ | ----------------------------- | -------------------------------------------------------------------------- |
| Core         | `src/core/`                   | Persona、Team ABC、メモリ、LLM クライアント                                            |
| Environment  | `src/environment/`            | scrubber: `SimulatorProtocol`、EPS mock。ssos: `EclssBackend`、`graph_rewire` |
| Scenario     | `src/scenario/`               | 各シナリオ YAML、Team、`design_proposals`                                         |
| Experiments  | `src/experiments/results/`    | 実行出力                                                                       |
| Tools        | `src/tools/dashboard/`        | Streamlit（`summary.scenario` でビュー分岐）                                       |
| Integrations | `src/integrations/one_piece/` | provenance JSON                                                            |


### エージェントチーム（両系統共通）

`Team` ABC を継承。硬直ロールではなく **同種 N 体 + 代表 action**。


| 概念           | 説明                                       |
| ------------ | ---------------------------------------- |
| `team.count` | オペレータ数（scrubber デフォルト 4、ssos デフォルト 3）    |
| deliberation | llm: 全員 1 ラウンド。labeled: ルールが定型メッセージ      |
| action rep   | step ごとに `(step-1) % N` で代表がコマンド発行       |
| post-run rep | 最終 step の代表が `design_proposals.json` を出力 |
| 設計分離         | **ランタイム中は恒久グラフを変えない**。事後提案のみ             |


詳細: [memo/homogeneous_agent_team_plan.md](../memo/homogeneous_agent_team_plan.md)。

### `agents.mode`（両系統共通の値）


| モード                 | 意味                                |
| ------------------- | --------------------------------- |
| `none`              | バックエンドのみ（エージェントなし）                |
| `labeled_rule_base` | `policy` / 閾値駆動                   |
| `llm`               | Ollama deliberation + 代表 action   |
| `base`              | 未実装（[BL-001](../memo/backlog.md)） |


LLM プロンプトに `**policy` 閾値を含めない**（公平な比較実験のため）。

### 実装ステータス


| 機能                    | scrubber           | ssos                                                                           |
| --------------------- | ------------------ | ------------------------------------------------------------------------------ |
| シナリオ + チーム            | ✅ 凍結               | ✅ Phase 0–7                                                                    |
| labeled / llm         | ✅                  | ✅                                                                              |
| ダッシュボード               | ✅ ppm / EPS / トポロジ | ✅ ストレージ / 運用 TL                                                                |
| provenance            | ✅ EPS 回復           | ✅ 運用コマンド                                                                       |
| 事後提案 → provenance     | 📋 未               | 📋 未                                                                           |
| CLI 統合                | 📋 未               | 📋 未                                                                           |
| launch remap（Phase 8） | —                  | 📋 [BL-003](../memo/backlog.md#bl-003-ros-launch-remapphase-8--graph_rewire-a) |


---

## scrubber_degradation

Python モック上の CO₂ スクラバー異常。**凍結済み** — 新機能は `ssos_eclss_loop` 側へ。

### 用語


| 略称                  | 説明                                       |
| ------------------- | ---------------------------------------- |
| **ECLSS**           | 生命維持プラント（スクラバー・マニホールド・cabin）             |
| **EPS**             | 発電・蓄電・配電。`request_eps_boost` で ECLSS を支援 |
| **SARJ** / **BCDU** | 太陽発電・蓄電放電モック（`MockSarj` / `MockBcdu`）    |


### 実行フロー

```text
scenario.yaml + agents.yaml
        │
        ▼
  scenario/runner.py → ScrubberDegradationScenario
        │
        ├─ build_simulator() → StationSimulator(ECLSS + EPS)
        ├─ build_team()      → ScrubberDegradationTeam
        │
        ▼
  for step in 1..N:
    1. sim.step()                    → TelemetrySnapshot
    2. log telemetry, health, design_state
    3. team.run_step(sim, obs)       → RecoveryCommand
    4. team.apply_outcome(sim, ...)  → apply_command のみ
    5. log messages, events
        │
        ▼
  propose_post_run_design() → design_proposals.json
  export_run_provenance()   → recovery レコード
```

### ランタイム vs 事後


| フェーズ  | 内容                          | 出力                      |
| ----- | --------------------------- | ----------------------- |
| ランタイム | 回復コマンド（ファン、負荷、EPS、バイパス）     | `recovery_applied`      |
| 事後    | scrubber トポロジ提案（シミュには適用しない） | `design_proposals.json` |


`design_state.jsonl` のトポロジは run 中不変。ダッシュボードの After プレビューは提案の**仮適用**。

### ECLSS + EPS スタック

```text
StationSimulator
  ├─ MockEclssSimulator   CO₂ ppm、スクラバー、ファン、バイパス
  └─ EpsStack
       ├─ MockSarj
       └─ MockBcdu          request_eps_boost 応答
```

トポロジ:

```text
  cabin ──flow──► manifold ──flow──► scrubber ──flow──► cabin
                                        ▲
                                        │ power
                                   power_bus
```

### ヘルス（ppm / 電力）

`compute_health_metrics()` — `src/environment/eclss_ops/telemetry.py`


| 指標         | safe  | warning       | critical |
| ---------- | ----- | ------------- | -------- |
| CO₂ (ppm)  | < 800 | 800 〜 1200 未満 | ≥ 1200   |
| 電力マージン (W) | > 0   | 0 〜 −150 未満   | ≤ −150   |


`policy.co2_recovery_ppm`（1000 等）は回復トリガーであり、ヘルス区分とは別。

### エージェント


| `agents.mode`       | ランタイム                   | 事後          | テスト                            |
| ------------------- | ----------------------- | ----------- | ------------------------------ |
| `none`              | シミュのみ                   | —           | `test_scrubber_baseline.py`    |
| `labeled_rule_base` | policy 駆動回復             | bypass 提案   | `test_scrubber_with_agents.py` |
| `llm`               | deliberation + commands | LLM changes | 同上（Fake LLM）                   |


#### labeled_rule_base


| 挙動                                  | トリガー                         |
| ----------------------------------- | ---------------------------- |
| `set_fan_speed`                     | CO₂ ≥ `co2_recovery_ppm`     |
| `reduce_load` / `request_eps_boost` | 電力 critical                  |
| `enable_bypass`                     | CO₂ 高 + ファン済み                |
| 事後 bypass 提案                        | peak CO₂ 高 or `anomaly_seen` |


#### llm

1. Deliberation（全 N 体）→ 2. Action（代表 `commands`）→ 3. Post-run（`changes`）

プロンプト: `### Telemetry` + `### World state`（policy なし）

### 出力・ダッシュボード


| 固有ファイル                | 内容                    |
| --------------------- | --------------------- |
| `eps_telemetry.jsonl` | SARJ + BCDU           |
| `events.jsonl`        | 異常、`recovery_applied` |



| ビュー         | 内容                               |
| ----------- | -------------------------------- |
| Overview    | CO₂ ppm、電力、EPS、トポロジ Before/After |
| Step replay | 回復タイムライン、reasoning               |


run ID: `scrubber_degradation_{baseline|labeled_rule_base|llm}`

---

## ssos_eclss_loop

SSOS Docker 内の実 ROS2 ECLSS（または `LoopMockEclssBackend`）。`**SimulatorProtocol` は使わない**。

### 用語


| 略称      | 説明                                                |
| ------- | ------------------------------------------------- |
| **ARS** | Air Revitalisation — CO₂ 除去（`air_revitalisation`） |
| **OGS** | Oxygen Generation — O₂ 生成（`oxygen_generation`）    |
| **WRS** | Water Recovery — 水回収（`water_recovery_systems`）    |


### 実行フロー

```text
scenario.yaml + agents.yaml (+ ssos_graph.rewires 任意)
        │
        ▼
  scenario/ssos_eclss_loop/scenario_run.py
        │
        ├─ build_eclss_backend() → LoopMockEclssBackend | Ros2EclssBridge(topic_remap)
        ├─ build_team()            → SsosEclssLoopTeam
        │
        ▼
  for step in 1..N:
    1. backend.poll_telemetry()      → EclssTelemetrySnapshot
    2. log telemetry, health, design_state
    3. team.run_step(backend, obs)  → EclssOperationalCommand
    4. team.apply_outcome(...)      → Action/Service、re-arm 判定
    5. log messages, operational events
        │
        ▼
  propose_post_run_design() → design_proposals.json（ssos_graph）
  export_run_provenance()   → operational レコード
```

### ランタイム vs 事後


| フェーズ  | 内容                                     | 出力                      |
| ----- | -------------------------------------- | ----------------------- |
| ランタイム | ARS/OGS/WRS 運用コマンド                     | `operational_applied`   |
| 事後    | `action_profile` / `graph_rewire` 等の提案 | `design_proposals.json` |


**graph_rewire（Phase 7）**: 次 run の `Ros2EclssBridge` に client `topic_remap`。launch remap（Phase 8）はバックログ。

### ECLSS スタック

```text
SsosEclssLoopTeam
  └─ EclssBackend
       ├─ LoopMockEclssBackend   ホスト dev（簡易ストレージ動態）
       └─ Ros2EclssBridge        SSOS Docker — ros2 CLI
            └─ topic_remap       graph_rewire
```

```text
  代謝 CO₂ ──► /co2_storage ──► ARS
  /o2_storage ◄── OGS ◄── request_co2 (Sabatier)
  /wrs/product_water_reserve ◄── WRS
```

`run_ssos_eclss_loop.sh` / `ea-loop` でコンテナ内実行。ECLSS headless 起動が前提。

### ヘルス（ストレージ kg）

`compute_eclss_storage_health()` — `src/scenario/ssos_eclss_loop/health.py`


| 指標       | safe   | warning        | critical |
| -------- | ------ | -------------- | -------- |
| CO₂ (kg) | < 1500 | 1500 〜 2200 未満 | ≥ 2200   |
| O₂ (kg)  | > 450  | 337.5 〜 450    | ≤ 337.5  |
| 製品水 (L)  | > 50   | 25 〜 50        | ≤ 25     |


`thresholds.co2_storage_high_kg` 等は運用トリガー。ヘルス区分とは別。

### エージェント


| `agents.mode`       | ランタイム                      | 事後           | テスト                                |
| ------------------- | -------------------------- | ------------ | ---------------------------------- |
| `none`              | poll のみ                    | —            | `test_ssos_eclss_loop_scenario.py` |
| `labeled_rule_base` | 閾値 → ARS/OGS               | `ssos_graph` | `test_ssos_eclss_loop_team.py`     |
| `llm`               | deliberation + operational | LLM changes  | 同上                                 |


#### labeled_rule_base

`thresholds`（scenario.yaml）+ `policy` プロファイル（agents.yaml）。閾値は `merge_labeled_policy_from_thresholds()` でマージ。


| 挙動                   | トリガー                         |
| -------------------- | ---------------------------- |
| `air_revitalisation` | CO₂ ≥ high、ARS 未起動           |
| `request_co2`        | O₂ ≤ low、OGS 前（policy 既定 ON） |
| `oxygen_generation`  | O₂ ≤ low、OGS 未起動             |
| re-arm               | 改善なければ次 step で再試行            |


#### llm

scrubber と同パターン。プロンプトにはストレージ kg とヘルス状態（policy なし）。

### 出力・ダッシュボード


| 固有フィールド                             | 内容                    |
| ----------------------------------- | --------------------- |
| `summary.backend`                   | `mock` / `ros2`       |
| `summary.operational_command_count` | 運用コマンド数               |
| `events.jsonl`                      | `operational_applied` |


**scrubber に無い**: `eps_telemetry.jsonl`、ppm ベース KPI。


| ビュー（`ssos_views.py`） | 内容                       |
| -------------------- | ------------------------ |
| Overview             | ストレージ kg、ヘルスカード、2 run 比較 |
| Step replay          | 運用タイムライン、`ssos_graph` 提案 |


run ID: `ssos_eclss_loop_{baseline|labeled_rule_base|llm}`

接合詳細: [memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](../memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md)

---

## 外部システム


| システム                   | 系統       | 状態                             |
| ---------------------- | -------- | ------------------------------ |
| Python モック ECLSS + EPS | scrubber | ✅ `StationSimulator`           |
| SSOS 実 ECLSS           | ssos     | ✅ `Ros2EclssBridge`            |
| SSOS EPS（scrubber 電力）  | scrubber | ✅ `Ros2EpsBridge`              |
| Ollama                 | 両方       | ✅ コンテナは `host.docker.internal` |
| One Piece Web UI       | —        | スコープ外                          |


---

## 開発セットアップ

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

回帰:

```bash
# scrubber
pytest tests/scenario/test_scrubber_baseline.py tests/scenario/test_scrubber_with_agents.py -q
# ssos
pytest tests/scenario/test_ssos_eclss_loop*.py tests/environment/test_graph_rewire*.py -q
```

SSOS コンテナ E2E: `./scripts/run_ssos_eclss_loop.sh`、`./scripts/run_graph_rewire_e2e.sh`

次の実装: [development-plan.md](development-plan.md) · API 詳細: [api-contracts.md](api-contracts.md)