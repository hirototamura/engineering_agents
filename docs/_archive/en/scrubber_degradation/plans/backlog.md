# Development backlog

## BL-005: SSOS EPS ROS2 bridge — follow-ups { #bl-005 }

**Status**: Phase 3a complete (PR-1–4), remainder not started  
**Related**: [ssos_eps_ros2_connection_plan.md](ssos_eps_ros2_connection_plan.md)

### Complete (reference)

- `EpsBackend` / `Ros2EpsBridge` / `topic_map.py` / `build_eps_backend()`
- `request_eps_boost` **interim 3a** — when BCDU `discharging`, `current_draw * bus_voltage` + bridge timer
- `scripts/run_ssos_eps_smoke.sh`

### Not started

| Priority | Item | Description |
|----------|------|-------------|
| P2 | **PR-5 operations docs** | `docs/ssos-eps-integration.md` (separate PR) |
| P2 | **Phase 3b — direct BCDU discharge** | Call `/battery/battery_bms_*/discharge` services from bridge |
| P3 | **Phase 3c — `/bcdu/operation` Action** | SSOS upstream PR. Currently README only, not implemented |
| P3 | **Mac host↔container DDS** | CycloneDDS Peers, etc. Container-only execution for now |
| P2 | **Ongoing topic contract alignment** | Keep `eps_topics.py` in sync with SSOS real names (`/solar_controller/ssu_voltage_v`, etc.) |
| P2 | **EPS BCDU action (scrubber 3b)** | Discharge/boost Action path in `Ros2EpsBridge` (currently topic + command only) |

### Known limitations (3a interim)

- `/bcdu/operation` not implemented — discharge depends on SSOS auto thresholds + bridge timer
- `support_w` not in SSOS messages — bridge estimates watts
- ECLSS remains `MockEclssSimulator` on scrubber path (ECLSS+EPS single scenario is BL-004)

---
