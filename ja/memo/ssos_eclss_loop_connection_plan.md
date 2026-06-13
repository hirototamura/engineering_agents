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
| `src/environment/ssos/eclss_types.py` | `ArsGoal`, `EclssSmokeReport` |
| `src/scripts/ssos_eclss_ars_smoke.py` | コンテナ内スモーク（topic/action 確認 + goal 送信） |

```bash
# コンテナ内（ECLSS 起動済み）
source ~/ssos_ws/install/setup.bash
cd /path/to/engineering_agents
PYTHONPATH=src python3 -m scripts.ssos_eclss_ars_smoke
```

---

## 長期バックログ

- SSOS ECLSS に CO2 スクラバノード追加（upstream）
- それに合わせた別 Mock シナリオ（scrubber_degradation とは別）

---

## 関連

- [ssos_eps_ros2_connection_plan.md](ssos_eps_ros2_connection_plan.md)
- [docs/api-contracts.md](../docs/api-contracts.md)
- Cursor plan: `ssos_ars_agent_plan_e6782b7f.plan.md`
