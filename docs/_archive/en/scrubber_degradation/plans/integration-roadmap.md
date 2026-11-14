# EPS integration history

## Phase 3 — EPS ✅

**Deliverables**

| File | Role |
| --- | --- |
| `src/environment/scrubber/eps/backend.py` | Protocol |
| `src/environment/scrubber/eps/mock/backend.py` | Mock wrapper |
| `src/environment/ssos/eps/ros2/bridge.py` | CLI bridge |
| `src/environment/ssos/eps/ros2/topic_map.py` | SSOS live topic map |
| `src/environment/ssos/eps/ros2/adapters.py` | BCDU parsing |
| `src/environment/scrubber/station_simulator.py` | Refactored to use `EpsBackend` |
| `src/scripts/ssos_eps_smoke.py` | EPS smoke |
| `scripts/run_ssos_eps_smoke.sh` | Wrapper |

`scenario/runner.py`: `build_eps_backend()` — `mock` \| `ssos_eps`

Historical phase record. See [EPS integration](../../../../en/developers/scenarios/scrubber_degradation/implementation.md) for the current contract.

### Phase 3 Deliverables (complete — `3b4b0b4`)

Details: [ssos_eps_ros2_connection_plan.md](ssos_eps_ros2_connection_plan.md)

| File | Role |
|----------|------|
| `src/environment/ssos/eps_backend.py` | `EpsBackend` Protocol |
| `src/environment/ssos/mock_eps_backend.py` | Mock SARJ + BCDU |
| `src/environment/ssos/ros2_eps_bridge.py` | SSOS EPS topic CLI bridge |
| `src/environment/ssos/topic_map.py` | Real plant topic name map |
| `src/environment/ssos/message_adapters.py` | BCDU / SARJ message parsing |
| `src/environment/ssos/station_simulator.py` | Power integration via `EpsBackend` |
| `src/environment/ssos/adapter.py` | `build_ssos_eps_station()` helper |
| `src/scenario/runner.py` | `build_eps_backend()` — `mock` \| `ssos_eps` |
| `src/scripts/ssos_eps_smoke.py` | EPS smoke |
| `scripts/run_ssos_eps_smoke.sh` | Wrapper |

```bash
./scripts/run_ssos_eps_smoke.sh
```
