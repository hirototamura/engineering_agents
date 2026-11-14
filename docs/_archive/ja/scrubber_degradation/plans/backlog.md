# 開発バックログ

## BL-005: SSOS EPS ROS2 ブリッジ — フォローアップ { #bl-005 }

**ステータス**: Phase 3a 完了（PR-1〜4）、残り未着手  
**関連**: [ssos_eps_ros2_connection_plan.md](ssos_eps_ros2_connection_plan.md)

### 完了済み（参照）

- `EpsBackend` / `Ros2EpsBridge` / `topic_map.py` / `build_eps_backend()`
- `request_eps_boost` **interim 3a** — BCDU `discharging` 時 `current_draw * bus_voltage` + bridge タイマー
- `scripts/run_ssos_eps_smoke.sh`

### 未着手

| 優先 | 項目 | 説明 |
|------|------|------|
| P2 | **PR-5 運用ドキュメント** | `docs/ssos-eps-integration.md`（別 PR） |
| P2 | **Phase 3b — BCDU discharge 直接呼び出し** | `/battery/battery_bms_*/discharge` サービスを bridge から呼ぶ |
| P3 | **Phase 3c — `/bcdu/operation` Action** | SSOS upstream PR。現状 README のみで未実装 |
| P3 | **Mac ホスト↔コンテナ DDS** | CycloneDDS Peers 等。当面はコンテナ内実行に限定 |
| P2 | **トピック契約の継続整合** | `eps_topics.py` と SSOS 実名（`/solar_controller/ssu_voltage_v` 等）のドキュメント同期 |
| P2 | **EPS BCDU action（scrubber 3b）** | `Ros2EpsBridge` で discharge/boost の Action 経路（現状 topic + command のみ） |

### 既知の制限（3a interim）

- `/bcdu/operation` 未実装 — discharge は SSOS 自動閾値 + bridge タイマー依存
- `support_w` は SSOS メッセージにない — bridge が watt 推定で補完
- ECLSS は scrubber 経路では引き続き `MockEclssSimulator`（ECLSS+EPS 単一シナリオは BL-004）

---
