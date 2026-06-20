# SSOS ECLSS ループ接合プラン

> **対象**: Space Station OS ECLSS（ARS / OGS / WRS）を `engineering_agents` エージェントが Crew Simulation の代わりに操作する。`scrubber_degradation` は Mock 凍結のまま別シナリオ。

---

## 実装状況（2026-06-14 更新）

| 項目 | 値 |
|------|-----|
| ブランチ | `feat/ssos-eclss-loop`（draft PR #9 vs `main`） |
| 作業ツリー（未コミット） | — |
| 最新コミット | `d62ca77` — Phase 6 LLM + コンテナ ros2/Ollama デフォルト |
| Phase コミット列 | `e18e79a` 1a/1b → `2700fda` WRS → `3b4b0b4` EPS → `7196812`/`b2b64f9` シナリオ → `797b589`/`d5bf9af` design_proposals |
| テスト | `pytest` → **110+ passed**, 3 skipped（ROS2 統合は SSOS コンテナ外 skip） |
| **Phase 0–6** | **コード完了** — ros2 E2E 記録済（`ja/memo/e2e_records/`） |

| ユーザ向けドキュメント | ブランチ **`docs/ssos-mkdocs`**（MkDocs。`12267a4` は本ブランチから revert 済み） |
| ドキュメント保守 | 別エージェント — `docs/ssos-mkdocs` 上の `docs/MAINTENANCE.md` |

### マイルストーン一覧

| Phase | 内容 | 状態 |
|-------|------|------|
| **0** | DesignChange 削除 | ✅ 完了 |
| **1a–1b** | ARS / OGS smoke + `EclssBackend` | ✅ 完了 |
| **2** | WRS ブリッジ | ✅ 完了 |
| **3** | EPS 接合（scrubber 電力） | ✅ 完了 |
| **4** | `ssos_eclss_loop` + `SsosEclssLoopTeam`（labeled_rule_base） | ✅ 完了 |
| **5** | `design_proposals.json` + `--apply-proposals` | ✅ 完了 |
| **6** | LLM エージェント（deliberation + operational + 事後 design） | ✅ 完了 (`d62ca77`) |
| **6.1** | Docker 実行 UX（`ea-loop` デフォルト ros2 + Ollama `host.docker.internal`） | ✅ 完了 (`d62ca77`) |

---

## 合意事項（Phase 0 完了）

| 項目 | 状態 |
|------|------|
| ランタイム `DesignChange` | **削除済み** — `SimulatorProtocol.apply_design_change` なし |
| scrubber_degradation | **凍結** — 事後 `design_proposals.json`（dict）とダッシュボード After プレビューは維持 |
| 新シナリオ | `ssos_eclss_loop` — **実装済み**（`7196812`） |
| 事後提案（新） | `design_proposals.json`（`design_domain: ssos_graph`）— **実装済み**（Phase 5） |

---

## 段階的ロールアウト

| Phase | 内容 | 状態 | 完了条件 |
|-------|------|------|----------|
| **0** | DesignChange 削除 | **完了** | scrubber テスト全 pass |
| **1a** | ARS ヘッドレス smoke | **完了** | Docker 内 `python3 -m scripts.ssos_eclss_ars_smoke` |
| **1b** | ARS + OGS | **完了** | O₂/CO₂ Sabatier 競合が telemetry に現れる |
| **2** | + WRS | **完了** (`2700fda`) | `run_ssos_eclss_2_smoke.sh`、水トレードオフ信号 |
| **3** | EPS 接合 | **完了** (`3b4b0b4`) | [ssos_eps_ros2_connection_plan.md](ssos_eps_ros2_connection_plan.md)、`run_ssos_eps_smoke.sh` |
| **4** | `ssos_eclss_loop` + `SsosEclssLoopTeam` | **完了** (`7196812`) | mock/ros2 シナリオ、telemetry JSONL |
| **5** | `design_proposals.json` + 次 run 適用 | **完了** (`d5bf9af`) | `--apply-proposals`、ラン終了時に JSON 出力 |
| **6** | LLM エージェント（`SsosEclssLoopTeam`） | **完了**（未コミット） | mock pytest + コンテナ ros2 手動 E2E |
| **6.1** | Docker 実行 UX | **完了**（未コミット） | `ea-loop` デフォルト `ros2`、Ollama ホスト到達 |

---

## Action/Service — C++ 再ビルド要否

**既存 SSOS インターフェースに対する提案は rclpy のみで適用可能（再ビルド不要）。**

| 提案種別 | 適用方法 |
|----------|----------|
| `action_profile` | `ActionClient.send_goal()` — goal フィールドは毎回指定 |
| `service_config` | `ServiceClient.call()` |
| `set_parameter` | 次 run の launch YAML 差し替え（C++ は起動時読込） |
| 新 Action/Service/BT | SSOS upstream PR（fork 必要） |

### 既存インターフェース

- **Actions**: `air_revitalisation`, `water_recovery_systems`, `oxygen_generation`
- **Services**: `/ogs/request_o2`, `wrs/product_water_request`, `/ars/request_co2`, `/grey_water`
- **Topics**: `/co2_storage`, `/o2_storage`, `/wrs/product_water_reserve`, diagnostics, self_diagnosis

### Action/Service 型（Phase 1a 修正済み）

現行 SSOS Jazzy イメージでは型プレフィックスは **`space_station_interfaces`**（`space_station_eclss` ではない）。

| 種別 | 型 |
|------|-----|
| ARS Action | `space_station_interfaces/action/AirRevitalisation` |
| OGS Action | `space_station_interfaces/action/OxygenGeneration` |
| WRS Action | `space_station_interfaces/action/WaterRecovery` |
| O₂ / CO₂ Service | `space_station_interfaces/srv/O2Request`, `.../Co2Request` |
| Product water / Grey water | `space_station_interfaces/srv/RequestProductWater`, `.../GreyWater` |

定数は `src/environment/ssos/eclss_topics.py` に集約。

---

## アーキテクチャ

```
SsosEclssLoopTeam → scenario_run → EclssBackend
                                      ├── MockEclssBackend (dev)
                                      └── Ros2EclssBridge (SSOS Docker)
```

起動: `ros2 launch space_station eclss.launch.py`（crew GUI なし）

### Phase 1a 成果物（完了）

| ファイル | 役割 |
|----------|------|
| `src/environment/ssos/eclss_topics.py` | SSOS ECLSS Action/Service/Topic 定数（`space_station_interfaces/...`） |
| `src/environment/ssos/eclss_types.py` | `ArsGoal`, `EclssSmokeReport`, Phase 1b 型 |
| `src/scripts/ssos_eclss_ars_smoke.py` | コンテナ内スモーク（topic/action 確認 + goal 送信） |
| `scripts/run_ssos_eclss_smoke.sh` | ホスト Mac から `docker exec` 経由で 1a を実行 |

#### Phase 1a 検証手順（2 ターミナル）

**前提**: SSOS Docker コンテナが起動していること。本機の例: コンテナ名 `ssos`、イメージ `ghcr.io/space-station-os/space_station_os:latest`（`docker ps` で確認）。`engineering_agents` はコンテナに自動マウントされないため、スクリプトが `docker cp` で `src/` を `/tmp/engineering_agents/src` に同期する。

**Terminal 1 — ECLSS ヘッドレス起動（コンテナ内）**

```bash
docker exec -it ssos bash
bash /root/ssos-eclss-headless.sh
# Ctrl+C で停止。別シェルで smoke を回す間は起動したままにする。
```

**Terminal 2 — smoke（ホスト Mac の repo ルート）**

```bash
cd /path/to/engineering_agents
chmod +x scripts/run_ssos_eclss_smoke.sh   # 初回のみ
./scripts/run_ssos_eclss_smoke.sh
# JSON 保存: ./scripts/run_ssos_eclss_smoke.sh --json-out /tmp/eclss_smoke.json
```

ホスト `.venv` で `PYTHONPATH=src python3 -m scripts.ssos_eclss_ars_smoke` を実行すると **`ros2 CLI not found` で失敗するのは想定どおり**（Mac ホストに ROS 2 がないため）。コンテナ内では `PYTHONPATH=src` だけを設定すると ROS workspace の `PYTHONPATH` を上書きして `ros2` が壊れる — **`PYTHONPATH=/tmp/engineering_agents/src:$PYTHONPATH` のように prepend すること**（ラッパーが自動で行う）。

**手動（ラッパーなし）**

```bash
docker exec ssos mkdir -p /tmp/engineering_agents
docker cp src/. ssos:/tmp/engineering_agents/src/
docker exec -it ssos bash -lc '
  source /opt/ros/jazzy/setup.bash
  source ~/ssos_ws/install/setup.bash
  cd /tmp/engineering_agents
  PYTHONPATH=/tmp/engineering_agents/src:\${PYTHONPATH} python3 -m scripts.ssos_eclss_ars_smoke
'
```

**合格条件**: exit code 0、`/co2_storage` と `/ars/diagnostics` topic、`air_revitalisation` action が存在し、goal が SUCCEEDED。

**トラブルシュート**: `send_goal` が "Waiting for an action server..." で止まる場合、action **名前**は見えていても **型**が違うことがある。現行 SSOS イメージでは `ros2 action send_goal` の型は `space_station_interfaces/action/AirRevitalisation`（`space_station_eclss/action/...` ではない）。確認: `ros2 node info /air_revitalisation | grep -A1 'Action Servers'`。

```bash
# コンテナ内（ECLSS 起動済み）— 上記ラッパーが同等
source ~/ssos_ws/install/setup.bash
cd /path/to/engineering_agents
PYTHONPATH=src python3 -m scripts.ssos_eclss_ars_smoke
```

### Phase 1b 成果物（完了 — ARS + OGS）

| ファイル | 役割 |
|----------|------|
| `src/environment/ssos/eclss_backend.py` | `EclssBackend` Protocol |
| `src/environment/ssos/mock_eclss_backend.py` | ローカル dev / 契約テスト用 |
| `src/environment/ssos/ros2_eclss_bridge.py` | `ros2` CLI ブリッジ（Docker 内 minimum）— Jazzy `ros2 service call` 出力パース対応 |
| `src/scripts/ssos_eclss_1b_smoke.py` | ARS+OGS ブリッジスモーク（telemetry + OGS goal + Sabatier 信号） |
| `scripts/run_ssos_eclss_1b_smoke.sh` | ホスト Mac から `docker exec` 経由で 1b を実行 |

**Phase 1b 完了条件**: O₂/CO₂ Sabatier 競合が `poll_telemetry()` に現れる（SSOS コンテナ + ECLSS 起動時）。

```python
from environment.ssos.mock_eclss_backend import MockEclssBackend
from environment.ssos.ros2_eclss_bridge import Ros2EclssBridge

backend = MockEclssBackend()  # tests / local
# backend = Ros2EclssBridge()  # SSOS Docker

snap = backend.poll_telemetry()
backend.send_air_revitalisation_goal(ArsGoal())
backend.send_oxygen_generation_goal(OgsGoal())
backend.request_o2(500.0)
backend.request_co2(100.0)
backend.set_subsystem_failure("ars", enabled=True)
```

#### Phase 1b 検証手順（2 ターミナル）

**前提**: Phase 1a と同様（コンテナ `ssos`、ECLSS ヘッドレス起動済み）。ラッパーは `src/` を `/tmp/engineering_agents/src` に同期する。

**Terminal 1 — ECLSS ヘッドレス起動（コンテナ内）**

```bash
docker exec -it ssos bash
bash /root/ssos-eclss-headless.sh
# 1b smoke 実行中は起動したままにする。
```

**Terminal 2 — 1b smoke（ホスト Mac の repo ルート）**

```bash
cd /path/to/engineering_agents
chmod +x scripts/run_ssos_eclss_1b_smoke.sh   # 初回のみ
./scripts/run_ssos_eclss_1b_smoke.sh
# JSON 保存: ./scripts/run_ssos_eclss_1b_smoke.sh --json-out /tmp/eclss_1b_smoke.json
```

**手動（ラッパーなし）**

```bash
docker exec ssos mkdir -p /tmp/engineering_agents
docker cp src/. ssos:/tmp/engineering_agents/src/
docker exec -it ssos bash -lc '
  source /opt/ros/jazzy/setup.bash
  source ~/ssos_ws/install/setup.bash
  cd /tmp/engineering_agents
  PYTHONPATH=/tmp/engineering_agents/src:\${PYTHONPATH} python3 -m scripts.ssos_eclss_1b_smoke
'
```

**合格条件**: exit code 0、`poll_telemetry()` で `/co2_storage` と `/o2_storage` が取得でき、`oxygen_generation` goal が SUCCEEDED、`request_co2` が成功し、O₂/CO₂ の Sabatier 競合信号（`sabatier_signal: true`）が JSON レポートに含まれる。

**トラブルシュート**: `request_co2` や `request_o2` が常に失敗する場合、Jazzy の `ros2 service call` 出力が YAML ではなく Python repr になることがある。`Ros2EclssBridge` は両形式をパースする（`067c576` で修正）。手動確認: `ros2 service call /ars/request_co2 space_station_interfaces/srv/Co2Request "{amount: 25.0}"`。

WRS Action/Service は Phase 2 で `Ros2EclssBridge` に追加済み（`2700fda`）。

### Phase 2 成果物（完了 — `2700fda`）

| ファイル | 役割 |
|----------|------|
| `src/environment/ssos/ros2_eclss_bridge.py` | WRS action、`request_product_water` / grey water service |
| `src/environment/ssos/mock_eclss_backend.py` | WRS mock + 水トレードオフ dynamics |
| `src/environment/ssos/eclss_types.py` | `WrsGoal` 等 |
| `src/scripts/ssos_eclss_2_smoke.py` | Phase 2 smoke（`water_tradeoff_signal`） |
| `scripts/run_ssos_eclss_2_smoke.sh` | ホスト Mac ラッパ |

**完了条件**: 飲料水 vs 電解水トレードオフが smoke JSON / telemetry に現れる。

```bash
./scripts/run_ssos_eclss_2_smoke.sh
```

### Phase 3 成果物（完了 — `3b4b0b4`）

詳細: [ssos_eps_ros2_connection_plan.md](ssos_eps_ros2_connection_plan.md)

| ファイル | 役割 |
|----------|------|
| `src/environment/ssos/eps_backend.py` | `EpsBackend` Protocol |
| `src/environment/ssos/mock_eps_backend.py` | Mock SARJ + BCDU |
| `src/environment/ssos/ros2_eps_bridge.py` | SSOS EPS トピック CLI ブリッジ |
| `src/environment/ssos/topic_map.py` | 実機トピック名マップ |
| `src/environment/ssos/message_adapters.py` | BCDU / SARJ メッセージパース |
| `src/environment/ssos/station_simulator.py` | `EpsBackend` 経由の電力連携 |
| `src/environment/ssos/adapter.py` | `build_ssos_eps_station()` ヘルパ |
| `src/scenario/runner.py` | `build_eps_backend()` — `mock` \| `ssos_eps` |
| `src/scripts/ssos_eps_smoke.py` | EPS smoke |
| `scripts/run_ssos_eps_smoke.sh` | ラッパ |

```bash
./scripts/run_ssos_eps_smoke.sh
```

### Phase 4 成果物（完了 — `7196812`）

| ファイル | 役割 |
|----------|------|
| `src/scenario/ssos_eclss_loop/scenario.yaml` | 設計・検証要求スタブ |
| `src/scenario/ssos_eclss_loop/agents.yaml` | エージェント設定 |
| `src/scenario/ssos_eclss_loop/scenario_run.py` | シナリオ runner |
| `src/scenario/ssos_eclss_loop/loop_mock_backend.py` | ループ mock dynamics |
| `src/scenario/ssos_eclss_loop/health.py` | 決定論的 health チェック |
| `src/scenario/agents/ssos_eclss_loop_team.py` | Crew Simulation 代替チーム |
| `src/scenario/agents/eclss_loop_types.py` | 提案・コマンド型 |
| `src/scenario/runner.py` | `_scenario_registry()` + `SsosEclssLoopTeam` |

#### Phase 4 / 5 / 6 実行（推奨手順）

**前提（コンテナ ros2）**: Terminal 1 で `bash /root/ssos-eclss-headless.sh`。Terminal 2 で loop。

**ホストから 1 コマンド**（sync + コンテナ内実行、backend は自動で ros2）:

```bash
./scripts/run_ssos_eclss_loop.sh --agents-mode labeled_rule_base
./scripts/run_ssos_eclss_loop.sh --agents-mode llm   # Mac 上 Ollama 必須
```

**コンテナに入って 1 コマンド**（初回のみホストで sync）:

```bash
# ホスト（1 回 — コード更新のたびに再実行）
./scripts/run_ssos_eclss_loop.sh --sync-only

# コンテナ内（ea-loop = /usr/local/bin/ea-loop → run.sh）
docker exec -it ssos bash
ea-loop --agents-mode labeled_rule_base    # backend デフォルト ros2
ea-loop --agents-mode llm                  # ros2 + host.docker.internal:11434
ea-loop --backend mock --agents-mode llm   # mock 上書き（開発用）
```

**mock（Docker / ROS 不要 — ホスト Mac）**:

```bash
./scripts/run_ssos_eclss_loop.sh --mock --agents-mode labeled_rule_base
./scripts/run_ssos_eclss_loop.sh --mock --agents-mode llm
# または
PYTHONPATH=src python3 -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode llm
```

**2 回目 — 前 run の design_proposals を適用**:

```bash
ea-loop --agents-mode labeled_rule_base \
  --apply-proposals /tmp/engineering_agents/src/experiments/results/ssos_eclss_loop_labeled_rule_base/design_proposals.json
```

**環境変数（コンテナ内 `ea-loop` が自動設定）**:

| 変数 | デフォルト（コンテナ） | 用途 |
|------|------------------------|------|
| `SSOS_ECLSS_BACKEND` | `ros2` | mock 上書き: `--backend mock` |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Mac ホスト Ollama（llm モード） |

ECLSS 未起動時は `ea-loop` が即エラー（空 ros2 グラフ検出）。

---

## Phase 5 成果物（完了 — `d5bf9af`）

| ファイル | 役割 |
|----------|------|
| `src/scenario/ssos_eclss_loop/design_proposals.py` | 読込・検証・apply プラグイン（`design_domain: ssos_graph`） |
| `scenario_run.py` | ラン終了時に `design_proposals.json` 出力、`--apply-proposals` |
| `scripts/run_ssos_eclss_loop.sh` | ホストラッパ（sync + exec / `--mock`） |
| `scripts/ssos_container_run.sh` | コンテナ内 `ea-loop` エントリ |

`change_kind`: `action_profile` | `service_config` | `set_parameter` | `graph_rewire`

---

## Phase 6 成果物（完了 — 作業ツリー、未コミット）

| ファイル | 役割 |
|----------|------|
| `src/scenario/agents/ssos_eclss_loop_team.py` | `_run_step_llm`（deliberation + action）、`propose_post_run_design` |
| `src/core/agents/persona.py` | `eclss_operational_action_contract` / `eclss_design_proposal_contract` |
| `src/core/llm/ollama.py` | `resolve_ollama_base_url()` — `OLLAMA_BASE_URL` 環境変数 |
| `src/core/agents/memory.py` | `EclssOperationalCommand` の payload 記録 |
| `tests/scenario/test_ssos_eclss_loop.py` | `test_ssos_eclss_loop_llm_agents_invoke_ars`（Fake LLM） |
| `tests/scenario/test_ssos_eclss_loop_team.py` | LLM パース単体テスト |

**LLM フロー**（scrubber パターン準拠）:

1. 全員 deliberation（`message_contract`）
2. action rep が operational コマンド（`eclss_operational_action_contract`）
3. ラン終了後 post-run design（`eclss_design_proposal_contract` → `design_proposals.json`、`decision_source: llm`）

**pytest（mock）**:

```bash
PYTHONPATH=src pytest tests/scenario/test_ssos_eclss_loop.py::test_ssos_eclss_loop_llm_agents_invoke_ars -q
```

**コンテナ E2E（ros2）— 記録済（2026-06-14）**: 詳細は [`ja/memo/e2e_records/README.md`](e2e_records/README.md)

| run | 結果 |
|-----|------|
| `labeled_rule_base` | `operational_command_count=2`、OGS SUCCEEDED |
| `llm`（3 steps） | Ollama 接続 OK、`decision_source=llm`、operational hold（CO₂=0） |

---

## 振り返り（2026-06-14）

### 達成したこと

1. **Mock → SSOS 実機への段階接合** — ARS/OGS/WRS smoke → `Ros2EclssBridge` → シナリオループまで一気通貫。
2. **scrubber との設計分離** — ランタイム topology 変更を廃止し、事後 `design_proposals.json` に統一（scrubber は mock topology、SSOS は `ssos_graph` ドメイン）。
3. **Crew Simulation 代替** — `SsosEclssLoopTeam` が labeled_rule_base と LLM の両方で ARS/OGS/CO₂ サービスを操作。
4. **Docker 開発 UX** — `ea-loop` 1 コマンド、sync スクリプト、ros2/Ollama のコンテナ向けデフォルト。

### 学んだこと / ハマりどころ

| 問題 | 原因 | 対策 |
|------|------|------|
| コンテナ内 `ModuleNotFoundError: scenario` | `src/` 未 sync | `run_ssos_eclss_loop.sh --sync-only` |
| `ea-loop` が mock のまま | `--backend` 未指定 + scenario.yaml デフォルト mock | `SSOS_ECLSS_BACKEND=ros2` を `ea-loop` に組込 |
| LLM 全部失敗・command 0 | コンテナ内 `localhost:11434` はホスト Ollama に届かない | `OLLAMA_BASE_URL=http://host.docker.internal:11434` |
| Mac ホストで ros2 smoke 失敗 | ホストに ROS 2 なし | **想定どおり** — コンテナ内実行 |
| SSOS トピック名 ≠ 初期契約 | 実機は `/solar_controller/ssu_voltage_v` 等 | `topic_map.py` / `eclss_topics.py` で定数化 |

### 未検証 / リスク

- **ARS 経路 on 実機** — SSOS 初期 CO₂=0 のため labeled/LLM とも ARS 未発火（OGS 経路で検証）
- **Ollama モデル** — `agents.yaml` の `gemma4:e4b` がホストに無いと LLM 失敗。
- **action 待ち** — ros2 ブリッジは CLI ベースで action timeout 120s。ステップ数が多いと遅い。
- **One Piece provenance** — ssos_eclss_loop では record 0 の報告あり（統合は別途）。

---

## 次へのアクション

### 即時（PR マージ前）

| # | アクション | 状態 |
|---|-----------|------|
| 1 | Phase 6 + 6.1 コミット & push | ✅ `d62ca77` |
| 2 | コンテナ E2E 記録 | ✅ `ja/memo/e2e_records/` |
| 3 | labeled_rule_base ros2 E2E | ✅ OGS + request_co2（events.jsonl） |
| 4 | draft PR #9 Ready for review | 実施中 |

### 短期バックログ（Phase 7 候補）

| 優先 | 項目 | 説明 |
|------|------|------|
| P1 | **ros2 E2E pytest（optional）** | SSOS コンテナ CI または `@pytest.mark.integration` |
| P1 | **LLM 接続 preflight** | llm モード開始時に `OllamaClient.check_connection()` で早期 fail |
| P2 | **WRS in scenario team** | labeled/LLM が WRS goal・水サービスを操作 |
| P2 | **ECLSS + EPS 単一 ros2 シナリオ** | 電力危機と ECLSS を同一 run |
| P2 | **3b — EPS BCDU action** | discharge/boost の Action 経路 |
| P3 | **rclpy ネイティブクライアント** | CLI ブリッジからの移行 |
| P3 | **MkDocs CI deploy** | `docs/ssos-mkdocs` ブランチ |
| P3 | **upstream CO₂ スクラバ** | SSOS ECLSS 拡張 → 新 Mock シナリオ |

### 推奨デモシナリオ（ハッカソン展示）

```bash
# 1. rule ベースで SSOS 実機操作 + design 提案
ea-loop --agents-mode labeled_rule_base

# 2. 提案を次 run に適用
ea-loop --agents-mode labeled_rule_base --apply-proposals .../design_proposals.json

# 3. LLM が同じ plant を判断（Ollama 起動済み）
ea-loop --agents-mode llm
```

---

## 次のプラン（Phase 7+）— 旧バックログ

| 項目 | 説明 |
|------|------|
| **3b — EPS BCDU action** | `Ros2EpsBridge` で discharge/boost の Action 経路（現状は topic + command のみ） |
| **WRS in scenario team** | `SsosEclssLoopTeam` が WRS goal / 水サービスを labeled_rule_base で操作 |
| **ECLSS + EPS 単一 ros2 シナリオ** | `ssos_eclss_loop` で `eclss.backend=ros2` と `eps.backend=ssos_eps` を同時に smoke |
| **MkDocs CI deploy** | `docs/ssos-mkdocs` ブランチで実施（`mkdocs gh-deploy` / Pages） |
| **rclpy ネイティブクライアント** | CLI ブリッジからの移行（レイテンシ・CI 安定性） |
| **upstream** | SSOS ECLSS への CO₂ スクラバノード追加 → 別 Mock シナリオ |

---

## 長期バックログ

- SSOS ECLSS に CO2 スクラバノード追加（upstream）— 上記バックログと重複、One Piece 連携後に再検討

---

## 関連

- [ssos_eps_ros2_connection_plan.md](ssos_eps_ros2_connection_plan.md)
- SSOS MkDocs 入口 — `docs/ssos-mkdocs` の `docs/ssos/index.md`
- [docs/api-contracts.md](../docs/api-contracts.md)
- Cursor plan: `ssos_ars_agent_plan_e6782b7f.plan.md`
