# SSOS ECLSS ループ接合プラン

> **対象**: Space Station OS ECLSS（ARS / OGS / WRS）を `engineering_agents` エージェントが Crew Simulation の代わりに操作する。`scrubber_degradation` は Mock 凍結のまま別シナリオ。

---

## 実装状況

| 項目 | 値 |
|------|-----|
| ブランチ | `feat/ssos-eclss-loop` |
| 最新コミット | `git log -1 --oneline`（ドキュメント分離後） |
| Phase コミット | `2700fda` Phase 2 WRS / `3b4b0b4` Phase 3 EPS / `7196812` Phase 4 シナリオ / `2c62f15` プラン更新 |
| テスト | `pytest` → **104 passed**, 3 skipped（2026-06-14） |
| Phase 0–4 | **完了** |
| Phase 5 | **完了** — `design_proposals.json`（`design_domain: ssos_graph`）+ `--apply-proposals` |
| Phase 6 | **未着手** — LLM エージェント（次のプラン参照） |

| ユーザ向けドキュメント | ブランチ **`docs/ssos-mkdocs`**（MkDocs。`12267a4` は本ブランチから revert 済み） |
| ドキュメント保守 | 別エージェント — `docs/ssos-mkdocs` 上の `docs/MAINTENANCE.md` |

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
| **5** | `design_proposals.json` + 次 run 適用 | **完了** | `--apply-proposals`、ラン終了時に JSON 出力 |
| **6** | LLM エージェント（`SsosEclssLoopTeam`） | 未着手 | `agents-mode llm` + Ollama で operational コマンド |

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

#### Phase 4 / 5 実行（簡略）

**ホストから 1 コマンド**（sync + コンテナ内実行）:

```bash
./scripts/run_ssos_eclss_loop.sh --agents-mode labeled_rule_base
```

**コンテナに入って 1 コマンド**（初回のみホストで sync）:

```bash
# ホスト（1 回）
./scripts/run_ssos_eclss_loop.sh --sync-only

# コンテナ内
docker exec -it ssos bash
ea-loop --agents-mode labeled_rule_base
```

**mock（Docker 不要）**:

```bash
./scripts/run_ssos_eclss_loop.sh --mock --agents-mode labeled_rule_base
```

**2 回目 — 前 run の design_proposals を適用**:

```bash
ea-loop --agents-mode labeled_rule_base \
  --apply-proposals /tmp/engineering_agents/src/experiments/results/.../design_proposals.json
# またはホストから ./scripts/run_ssos_eclss_loop.sh --apply-proposals ...
```

ECLSS ヘッドレス起動（別ターミナル）: `bash /root/ssos-eclss-headless.sh`

---

## 次のプラン（Phase 6+）

### Phase 6 — LLM エージェント（優先）

| 項目 | 内容 |
|------|------|
| 対象 | `SsosEclssLoopTeam._run_step_llm`（現状スタブ） |
| 推論 | `OllamaClient` — `agents.yaml` の `llm` 設定（scrubber パターン準拠） |
| 出力 | operational コマンド（ARS / OGS / request_co2）+ `design_proposals.json`（`decision_source: llm`） |
| 検証 | mock バックエンドで pytest；ros2 はコンテナ内 + `host.docker.internal:11434` 等 |
| 完了条件 | `agents-mode llm` で `operational_command_count` > 0、提案 JSON が valid |

```bash
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode llm
```

### Phase 5 成果物（完了）

| ファイル | 役割 |
|----------|------|
| `src/scenario/ssos_eclss_loop/design_proposals.py` | 読込・検証・apply プラグイン・ビルド |
| `scenario_run.py` | ラン終了時に `design_proposals.json` 出力、`--apply-proposals` |

```bash
# 1 回目
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode labeled_rule_base

# 2 回目 — 前 run の提案を適用
python -m scenario.ssos_eclss_loop.scenario_run \
  --backend mock --agents-mode labeled_rule_base \
  --apply-proposals src/experiments/results/ssos_eclss_loop_labeled_rule_base/design_proposals.json
```

### バックログ（Phase 6 以降）

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
