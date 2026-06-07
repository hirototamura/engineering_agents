# アーキテクチャ — ECLSS（Environmental Control and Life Support System）レジリエンス・ループ

**ECLSS**（Environmental Control and Life Support System / 環境制御・生命維持システム）と **EPS**（Electrical Power System / 電力系）をモックしたシミュレーションの、レイヤ構成・実行フロー・エージェント設計リファレンス。

> 利用手順は [README.md](../README.md)。未完了機能は [development-plan.md](development-plan.md)。

---

## 用語（初出）

| 略称 | 英語名 | 本リポジトリでの意味 |
| --- | --- | --- |
| **ECLSS** | Environmental Control and Life Support System | 乗員の生存に必要な**生命維持装置**（CO2 除去・送気・環境制御）。物理実験装置ではなく、閉鎖環境のプラントをグラフで表現 |
| **EPS** | Electrical Power System | 宇宙ステーションの発電・蓄電・配電。ECLSS などの負荷へ電力を供給 |
| **SARJ** | Solar Alpha Rotary Joint | 太陽電池アレイの向き制御・発電系。MVP では `MockSarj` で太陽電圧を模擬 |
| **BCDU** | Battery Charge/Discharge Unit | 蓄電池の充放電ユニット。`request_eps_boost` 時に放電して ECLSS を支援 |
| **MBSU** | Main Bus Switching Unit | 主バス切替。実 EPS の構成要素（本 MVP のモックには未個別実装） |
| **DDCU** | Direct Current-to-Direct Current Converter Unit | DC-DC 変換。実 EPS の構成要素（本 MVP のモックには未個別実装） |

---

## ミッション

宇宙ステーションの **生命維持装置（ECLSS）** における異常に対し、**エージェントチームが検知・対応し、事後に設計変更を提案する**までを、再現可能な Python 環境で検証する。

高忠実度の数値物理モデルや 3D グラフィックより、次を優先する:

- **構造化されたエージェント関係**（同種チーム、代表 action、議論ログ）
- **シミュレータ API 契約**（`SimulatorProtocol`、JSONL、ROS2 風トピック）
- **SSOS のモック**（実軌道ソフトへの接続は別フェーズ）

本リポジトリは **Space Station OS（SSOS）をモックしたシミュレータ** 上で動作する。実機 ROS2 トピックへの接続は行わない。

---

## システム全体像

```text
┌─────────────────────────────────────────────────────────────┐
│  tools/          Streamlit dashboard, (将来) CLI              │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  scenario/       runner, YAML, ScrubberDegradationTeam        │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  environment/    StationSimulator, MockEclssSimulator, EPS    │
│                  SsosAdapter (stub)                           │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  core/           PersonaAgent, Team, memory, Ollama client    │
└─────────────────────────────────────────────────────────────┘

  integrations/one_piece/  ← scenario 終了時に provenance エクスポート
```

**依存方向**（import は一方向のみ）:

```text
tools → scenario → environment → core
src/integrations/   （scenario から呼び出し）
```

---

## レイヤ責務

| レイヤ | パス | 責務 |
| --- | --- | --- |
| Core | `src/core/` | Persona、Team ABC、メモリ（`DiscourseBuffer` / `AgentMemory`）、LLM クライアント、イベントログ |
| Environment | `src/environment/` | `SimulatorProtocol`、ECLSS 生命維持プラント、EPS（SARJ/BCDU モック）、SSOS トピック定義、アダプタスタブ |
| Scenario | `src/scenario/` | シナリオ YAML、レジストリ、`ScrubberDegradationTeam` |
| Experiments | `src/experiments/results/` | 実行出力（gitignore 推奨） |
| Tools | `src/tools/dashboard/` | Streamlit UI |
| Integrations | `src/integrations/one_piece/` | provenance JSON エクスポート |

---

## 実装ステータス

| 機能 | 状態 | 主要成果物 |
| --- | --- | --- |
| リポジトリ構成 | 完了 | `src/` レイヤ、`core/agents/`、`scenario/` |
| シミュレータ | 完了 | `SimulatorProtocol`、`StationSimulator`、`MockEclssSimulator` |
| ベースラインシナリオ | 完了 | `scrubber_degradation/scenario.yaml`、回帰テスト |
| labeled_rule_base チーム | 完了 | `policy` 駆動、回復コマンド、事後 `design_proposals.json` |
| llm チーム | 完了 | Ollama、1 ラウンド deliberation + 代表 action |
| EPS 連動 | 完了 | `eps_telemetry.jsonl`、BCDU 放電、`request_eps_boost` |
| ダッシュボード | 完了 | Overview、Step replay、2 run 比較、設計提案グラフ |
| One Piece provenance | 部分完了 | ランタイム **回復** のみ。post-run 設計提案は未エクスポート |
| CLI | 未着手 | [development-plan.md](development-plan.md) |
| SSOS 実機アダプタ | スタブ | `SsosAdapter` |

---

## 実行フロー（scrubber_degradation）

```text
scenario.yaml + agents.yaml
        │
        ▼
  scenario/runner.py → ScrubberDegradationScenario
        │
        ├─ build_simulator() → StationSimulator(ECLSS + EPS)
        ├─ build_team()      → ScrubberDegradationTeam（mode ≠ none）
        │
        ▼
  for step in 1..N:
    1. sim.step()                         → TelemetrySnapshot
    2. log telemetry, health, design_state（エージェント行動前）
    3. team.run_step(sim, obs)            → messages, commands
    4. team.apply_outcome(sim, outcome)   → apply_command のみ（設計変更は適用しない）
    5. log messages, sim events
        │
        ▼
  team.propose_post_run_design()          → design_proposals.json
  export_run_provenance()               → provenance.jsonl
  write summary.json
        │
        ▼
  experiments/results/<run_id>/
```

### 重要な設計分離

| フェーズ | 何が起きるか | 出力 |
| --- | --- | --- |
| **ランタイム** | 一時的な回復コマンドのみ（ファン、負荷、EPS、バイパス） | `events.jsonl`（`recovery_applied`）、`messages.jsonl` |
| **ラン終了後** | 恒久設計の**提案**（シミュレータには適用しない） | `design_proposals.json` |

`design_state.jsonl` は各 step の**エージェント行動前**のトポロジ。ランタイム中にノード／エッジは変わらないため、全 step で同一グラフが続く（パラメータの一時変化はテレメトリ側）。

ダッシュボードの **After (if proposals applied)** は、`design_proposals.json` をベースラインに**仮適用**したプレビューであり、シミュレーション結果そのものではない。

---

## エージェントモード（`agents.mode`）

`scenario.yaml` の `agents.mode`。`none` 以外は `agents.yaml` を読み込む。

| モード | チーム | ランタイム | 事後設計 | テスト |
| --- | --- | --- | --- | --- |
| `none` | なし | 生命維持シミュのみ（エージェントなし） | なし | `test_scrubber_baseline.py` |
| `labeled_rule_base` | 同種 N 体 | `policy` 閾値で回復 | ルールで bypass 提案 | `test_scrubber_with_agents.py` |
| `llm` | 同種 N 体 | LLM deliberation + action | LLM が changes 提案 | 同上（Fake LLM） |
| `base` | — | 未実装 | — | BL-001 |

### 同種エンジニアチーム

- ID: `engineer_1` … `engineer_N`（`team.count`、デフォルト 4）
- **代表 action**: `engineer_{(step-1) % N}` がその step の回復コマンドを発行
- **事後 design**: 最終 step の代表が `propose_post_run_design()` を実行

硬直した役割（operator / design_engineer 固定）ではなく、step ごとに実行者をローテーションする設計。詳細: [memo/homogeneous_agent_team_plan.md](../memo/homogeneous_agent_team_plan.md)。

### labeled_rule_base

`agents.yaml` の `policy` を**このモードだけ**が参照。LLM コードパスは `policy` を読まない。

| 挙動 | トリガー（要約） |
| --- | --- |
| alert | CO2 ≥ `co2_recovery_ppm`（デフォルト 1000） |
| diagnosis | `anomaly_flags` 非空 |
| `set_fan_speed` | CO2 ≥ 閾値、未適用 |
| `reduce_load` | 電力 critical、未適用 |
| `request_eps_boost` | 電力 critical かつ EPS 支援残 step = 0 |
| `enable_bypass` | CO2 ≥ 閾値、ファン済み、バイパス未 |
| 事後 bypass 提案 | peak CO2 ≥ 閾値 または `anomaly_seen` |

### llm

各 step の LLM 呼び出し（最大 N+1 回）:

1. **Deliberation** — 全 N 体が `message` + `reasoning`（`deliberation_phase: deliberation`）
2. **Action** — 代表が `commands` 配列（`deliberation_phase: action`）
3. **Post-run**（ラン終了後 1 回）— 代表が `changes` を `design_proposals.json` へ

**Situation 注入**（プロンプト）:

- `### Telemetry` — CO2、効率、電力マージン、EPS 支援など数値
- `### World state` — safe / warning / critical の記述的健康状態
- **`policy` 閾値は含めない**（ルールの答えを漏らさない）

**メタデータ**（`messages.jsonl`）: `decision_source`（`llm` / `llm_parse_fail` / `llm_no_action`）、`parse_status`、`raw_response_excerpt` など。

---

## 生命維持（ECLSS）・電力（EPS）スタック

```text
StationSimulator
  ├─ MockEclssSimulator   生命維持プラント（CO2、スクラバー、ファン、バイパス、負荷）
  └─ EpsStack             EPS（Electrical Power System）
       ├─ MockSarj        SARJ 相当 — 太陽電圧（軌道モック）
       └─ MockBcdu        BCDU 相当 — 充放電、request_eps_boost 応答
```

実際の ISS 等では EPS に **MBSU**（Main Bus Switching Unit）や **DDCU**（Direct Current-to-Direct Current Converter Unit）も含まれる。本 MVP は scrubber シナリオに必要な SARJ/BCDU 連携に絞っている。

`request_eps_boost` が成功すると、一定 step 数 `eps_support_w` が ECLSS 電力マージンに加算される。`eps_telemetry.jsonl` に BCDU `mode`（`discharging` 等）が記録される。

### ヘルス閾値（`compute_health_metrics`）

定義: `src/environment/eclss_ops/telemetry.py`（`CO2_SAFE_PPM`、`CO2_WARNING_PPM`、`POWER_LOW_W`、`POWER_CRITICAL_W`）。

| 指標 | safe | warning | critical |
| --- | --- | --- | --- |
| CO2 (ppm) | < 800 | 800 〜 1200 未満 | ≥ 1200 |
| 電力マージン (W) | > 0 | 0 〜 −150 未満 | ≤ −150 |

`overall` は CO2 と電力の**より悪い方**（safe < warning < critical）。

**注意**: エージェントの回復ポリシー（`agents.yaml` の `co2_recovery_ppm: 1000` 等）はヘルス閾値とは別。labeled_rule_base はポリシー閾値でコマンドを打ち、ヘルスはテレメトリから独立に `health_metrics.jsonl` へ記録される。

---

## 出力レイアウト

`src/experiments/results/<run_id>/`

| ファイル | 内容 |
| --- | --- |
| `telemetry.jsonl` | 毎 step の生命維持テレメトリ |
| `health_metrics.jsonl` | CO2 / 電力 / overall |
| `eps_telemetry.jsonl` | SARJ + BCDU（`StationSimulator` 時） |
| `design_state.jsonl` | 毎 step 開始時点のトポロジ（不変） |
| `events.jsonl` | 異常、回復適用 |
| `messages.jsonl` | エージェント発言（labeled / llm） |
| `design_proposals.json` | ラン終了後の恒久設計案 |
| `provenance.jsonl` | One Piece 互換（現状は主に EPS 回復） |
| `summary.json` | KPI 一式 |

デフォルト run ID（`scenario.yaml`）:

| mode | run_id |
| --- | --- |
| `none` | `scrubber_degradation_baseline` |
| `labeled_rule_base` | `scrubber_degradation_labeled_rule_base` |
| `llm` | `scrubber_degradation_llm` |

スキーマ: [api-contracts.md](api-contracts.md)。シナリオ叙事: [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md)。

---

## ダッシュボード（`src/tools/dashboard/app.py`）

| ビュー | 機能 |
| --- | --- |
| **Overview** | 単一 run または 2 run 横並び。テレメトリプロット、step スライダー、トポロジ、設計提案プレビュー |
| **Step replay** | イベントタイムライン、キャッシュ済みプロット + step 縦線、発言・reasoning フィード |
| **Run comparison**（compare 時） | run 名付き列のメトリクス表、Δ（primary − compare）、回復コマンド比較 |

サイドバー: run 選択、`Compare with another run`、Overview / Step replay 切替。

スクリーンショット: [README.md](../README.md#一目でわかるダッシュボード)。

---

## 外部システム

| システム | MVP |
| --- | --- |
| SSOS | Python モック。`SsosAdapter` はスタブ |
| LLM | Ollama（`core/llm/ollama.py`）、デフォルト `gemma4:e4b` |
| One Piece | `provenance.jsonl` のみ。Web UI・post-run design エクスポートは未 |

---

## 開発セットアップ

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

回帰の最小セット:

```bash
pytest tests/scenario/test_scrubber_baseline.py -q
pytest tests/scenario/test_scrubber_with_agents.py -q
```

LLM 実ランは Ollama 必須。CI では Fake LLM で `llm` パスを検証。

次の実装: [development-plan.md](development-plan.md)。
