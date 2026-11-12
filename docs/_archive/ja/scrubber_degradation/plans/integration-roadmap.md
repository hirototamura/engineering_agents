# EPS 接合の履歴

## Phase 3 — EPS ✅

**成果物**

| ファイル | 役割 |
| --- | --- |
| `src/environment/scrubber/eps/backend.py` | Protocol |
| `src/environment/scrubber/eps/mock/backend.py` | Mock ラッパ |
| `src/environment/ssos/eps/ros2/bridge.py` | CLI ブリッジ |
| `src/environment/ssos/eps/ros2/topic_map.py` | SSOS 実トピックマップ |
| `src/environment/ssos/eps/ros2/adapters.py` | BCDU パース |
| `src/environment/scrubber/station_simulator.py` | `EpsBackend` 経由にリファクタ |
| `src/scripts/ssos_eps_smoke.py` | EPS smoke |
| `scripts/run_ssos_eps_smoke.sh` | ラッパ |

`scenario/runner.py`: `build_eps_backend()` — `mock` \| `ssos_eps`

当時の Phase 記録です。現行の接合契約は [EPS 統合](../../../../ja/developers/scenarios/scrubber_degradation/implementation.md) を参照してください。

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
