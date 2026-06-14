# SSOS ECLSS ループ接合プラン

> **対象**: Space Station OS ECLSS（ARS / OGS / WRS）を `engineering_agents` エージェントが Crew Simulation の代わりに操作する。`scrubber_degradation` は Mock 凍結のまま別シナリオ。

---

## 合意事項（Phase 0 完了）

| 項目 | 状態 |
|------|------|
| ランタイム `DesignChange` | **削除済み** — `SimulatorProtocol.apply_design_change` なし |
| scrubber_degradation | **凍結** — 事後 `design_proposals.json`（dict）とダッシュボード After プレビューは維持 |
| 新シナリオ | `ssos_eclss_loop`（未実装） |
| 事後提案（新） | `operational_proposals.json` — `set_parameter` / `action_profile` / `service_config` のみ |

---

## 段階的ロールアウト

| Phase | 内容 | 完了条件 |
|-------|------|----------|
| **0** | DesignChange 削除 | scrubber テスト全 pass |
| **1a** | ARS ヘッドレス smoke | Docker 内 `python3 -m scripts.ssos_eclss_ars_smoke` |
| **1b** | ARS + OGS | O₂/CO₂ Sabatier 競合が telemetry に現れる |
| **2** | + WRS | 飲料水 vs 電解水、grey water トレードオフ |
| **3** | EPS 接合 | [ssos_eps_ros2_connection_plan.md](ssos_eps_ros2_connection_plan.md) |
| **4** | `ssos_eclss_loop` シナリオ + `SsosEclssLoopTeam` | エージェントが Crew 代替 |
| **5** | `operational_proposals.json` + 次 run 適用 | `--apply-proposals` |

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

---

## アーキテクチャ

```
SsosEclssLoopTeam → scenario_run → EclssBackend
                                      ├── MockEclssBackend (dev)
                                      └── Ros2EclssBridge (SSOS Docker)
```

起動: `ros2 launch space_station eclss.launch.py`（crew GUI なし）

### Phase 1a 成果物

| ファイル | 役割 |
|----------|------|
| `src/environment/ssos/eclss_topics.py` | SSOS ECLSS Action/Service/Topic 定数 |
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

### Phase 1b 成果物（ARS + OGS）

| ファイル | 役割 |
|----------|------|
| `src/environment/ssos/eclss_backend.py` | `EclssBackend` Protocol |
| `src/environment/ssos/mock_eclss_backend.py` | ローカル dev / 契約テスト用 |
| `src/environment/ssos/ros2_eclss_bridge.py` | `ros2` CLI ブリッジ（Docker 内 minimum） |

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

WRS Action/Service は Phase 2 で `Ros2EclssBridge` に追加予定。

---

## 長期バックログ

- SSOS ECLSS に CO2 スクラバノード追加（upstream）
- それに合わせた別 Mock シナリオ（scrubber_degradation とは別）

---

## 関連

- [ssos_eps_ros2_connection_plan.md](ssos_eps_ros2_connection_plan.md)
- [docs/api-contracts.md](../docs/api-contracts.md)
- Cursor plan: `ssos_ars_agent_plan_e6782b7f.plan.md`
