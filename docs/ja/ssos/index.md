> English: [../../en/ssos/index.md](../../en/ssos/index.md)

# SSOS ECLSS + EPS 接合 — 概要

**ブランチ**: `main`（PR #9 マージ済み）

本ドキュメントは、Space Station OS（SSOS）の **ECLSS**（生命維持）と **EPS**（電力）を `engineering_agents` から操作するための接合レイヤを説明します。Crew Simulation GUI の代わりに、エージェントが `EclssBackend` / `EpsBackend` 経由で ARS・OGS・WRS および BCDU を制御します。

!!! note "スコープ"
    - **仮想検証**が主目的です。物理世界（軌道上実機）への接続は本デモのスコープ外です。
    - 参照シナリオ `scrubber_degradation` は **Mock 凍結**のままです。SSOS 接合は新シナリオ `ssos_eclss_loop` で検証します。
    - ランタイム中の恒久トポロジ変更（旧 `DesignChange`）は **Phase 0 で削除済み**です。

---

## なぜ接合するか

| 従来（Crew Simulation） | 接合後（engineering_agents） |
| --- | --- |
| 人間オペレータが GUI で ARS/OGS を操作 | AI エージェントが `EclssBackend` API で同操作を再現 |
| 合否が主観的になりうる | テレメトリ JSONL + 決定論的 `health_metrics` で検証 |
| 設計と運用が混在しやすい | ランタイムは **運用コマンドのみ**、恒久変更は事後提案（Phase 5 予定） |

エージェントは「物理シミュレータの代わりに LLM が合格を宣言する」**自作自演**になってはなりません。SSOS Docker 上の ROS 2 グラフから取得した生テレメトリを入力に、シナリオ YAML の閾値で pass/fail を決めます（[AGENTS.md](../AGENTS.md) 参照）。

---

## Tier Model

接合は段階的に深くなります。各 Tier は独立して smoke テスト可能です。

| Tier | Phase | 内容 | バックエンド | 検証 |
| --- | --- | --- | --- | --- |
| **T0** | 0 | `DesignChange` 削除、`scrubber_degradation` 凍結 | Mock のみ | `pytest` |
| **T1a** | 1a | ARS Action smoke | `ros2` CLI → SSOS | `run_ssos_eclss_smoke.sh` |
| **T1b** | 1b | ARS + OGS + Service | `Ros2EclssBridge` | `run_ssos_eclss_1b_smoke.sh` |
| **T2** | 2 | + WRS（飲料水 vs 電解水） | `Ros2EclssBridge` | `run_ssos_eclss_2_smoke.sh` |
| **T3** | 3 | EPS 読取 + `request_eps_boost` interim | `Ros2EpsBridge` | `run_ssos_eps_smoke.sh` |
| **T4** | 4 | `ssos_eclss_loop` シナリオ + エージェント | mock \| ros2 切替 | `scenario_run.py` |
| **T5** | 5 | `operational_proposals.json` + 次 run 適用 | — | 未着手 |

---

## アーキテクチャ

```mermaid
flowchart TB
  subgraph agents [scenario/ — エージェント層]
    Team[SsosEclssLoopTeam]
    Runner[SsosEclssLoopScenario]
  end

  subgraph backends [environment/ssos/ — バックエンド層]
    EclssProto[EclssBackend Protocol]
    EpsProto[EpsBackend Protocol]
    MockEclss[LoopMockEclssBackend / MockEclssBackend]
    Ros2Eclss[Ros2EclssBridge]
    MockEps[MockEpsBackend]
    Ros2Eps[Ros2EpsBridge]
  end

  subgraph ssos [SSOS Docker — ROS 2 Jazzy]
    ARS[air_revitalisation]
    OGS[oxygen_generation]
    WRS[water_recovery_systems]
    BCDU[/bcdu/status]
    Solar[/solar_controller/ssu_voltage_v]
  end

  Team --> Runner
  Runner --> EclssProto
  EclssProto --> MockEclss
  EclssProto --> Ros2Eclss
  Ros2Eclss -->|ros2 CLI| ARS
  Ros2Eclss --> OGS
  Ros2Eclss --> WRS

  subgraph scrubber [scrubber_degradation — 凍結]
    Station[StationSimulator]
    Station --> EpsProto
    EpsProto --> MockEps
    EpsProto --> Ros2Eps
    Ros2Eps -->|ros2 CLI| BCDU
    Ros2Eps --> Solar
  end
```

### 実行パスの違い

| シナリオ | シミュレータ | ECLSS | EPS |
| --- | --- | --- | --- |
| `scrubber_degradation` | `StationSimulator` | `MockEclssSimulator` | `mock` \| `ssos_eps` |
| `ssos_eclss_loop` | なし（`EclssBackend` 直接） | `mock` \| `ros2` | 未使用（Phase 4） |

---

## 主要ファイル一覧

| パス | 役割 |
| --- | --- |
| `src/environment/ssos/eclss_topics.py` | Action / Service / Topic 定数 |
| `src/environment/ssos/eclss_backend.py` | `EclssBackend` Protocol |
| `src/environment/ssos/mock_eclss_backend.py` | 契約テスト用 Mock |
| `src/environment/ssos/ros2_eclss_bridge.py` | SSOS ECLSS ブリッジ（CLI） |
| `src/environment/ssos/eps_backend.py` | `EpsBackend` Protocol |
| `src/environment/ssos/mock_eps_backend.py` | SARJ/BCDU Mock ラッパ |
| `src/environment/ssos/ros2_eps_bridge.py` | SSOS EPS ブリッジ（CLI） |
| `src/environment/ssos/topic_map.py` | SSOS 実トピック ↔ 契約名 |
| `src/environment/ssos/message_adapters.py` | ROS メッセージ ↔ dataclass |
| `src/scenario/ssos_eclss_loop/` | 新シナリオ（YAML + runner + health） |
| `src/scenario/agents/ssos_eclss_loop_team.py` | Crew 代替エージェント |
| `scripts/run_ssos_eclss_*.sh` | ホスト → Docker smoke ラッパ |
| `scripts/run_ssos_eps_smoke.sh` | EPS smoke ラッパ |

---

## 関連リンク

- [クイックスタート](quickstart.md) — 2 ターミナル手順
- [ECLSS 統合](eclss-integration.md) — トピック・アクション詳細
- [EPS 統合](eps-integration.md) — 電力ブースト interim 方式
- [ssos_eclss_loop シナリオ](scenario-eclss-loop.md) — mock / ros2 の実行
- [トラブルシューティング](troubleshooting.md)
- [ロードマップ](roadmap.md) — Phase 0–5 状態
- [API リファレンス](api-reference.md)
- 開発メモ: [SSOS ECLSS 接合プラン](../memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md), [SSOS EPS ROS2 接合プラン](../memo/ssos_eclss_loop/ssos_eps_ros2_connection_plan.md)
