# Development backlog

## BL-003: ROS launch remap (Phase 8 — graph_rewire A) { #bl-003 }

**Status**: Not started (after Phase 7 client remap complete)  
**Related**: [ssos_eclss_loop_connection_plan.md](ssos_eclss_loop_connection_plan.md) Phase 7a, [ssos_ros2_graph_design_investigation.md](../investigations/ssos_ros2_graph_design_investigation.md)

### Background

Phase 7a covers **client-side remap in `Ros2EclssBridge` only**. Without `--ros-args -r` / launch `remappings` (A) at SSOS node startup, **internal wiring such as OGS↔WRS does not change**. The hackathon demo path (ea-loop / labeled / LLM) works without A, but scrubber-style `add_edge` material-flow changes require A + (if needed) an rclpy gateway.

`ssos_graph.rewires` can be reused in Phase 8 (branch from the same JSON for bridge vs launch).

### Tier plan

| Tier | Effort | Change locations | Deliverables |
|------|--------|------------------|--------------|
| **8a PoC** | 1–2 days | Hand-written `remappings` in `~/dev/ssos/ssos-headless.launch.py` | Launch remap verification for one topic/service |
| **8b proposals→launch** | 3–5 days | engineering_agents + `~/dev/ssos/` per table below | `--apply-proposals` → remap on next headless start (**ECLSS restart required**) |
| **8c Gateway** | 1–2 weeks | `environment/ssos/gateways/` (e.g. grey_water_router), launch Node add, collision detection, container E2E | Flow changes close to scrubber-style `add_edge` |

### Files to touch in 8b (draft)

**engineering_agents**

| File | Changes |
|------|---------|
| `scenario/ssos_eclss_loop/design_proposals.py` | `graph_rewire` adds `target_node` / `remap_rules[]` (`public`/`backend` kept for bridge) |
| `environment/ssos/launch_remap.py` (new) | `ssos_graph.rewires` → launch `remappings` generation |
| `scenario/ssos_eclss_loop/scenario_run.py` | manifest export |
| `scripts/ssos_container_run.sh` | warn headless restart when manifest present |

**~/dev/ssos/**

| File | Changes |
|------|---------|
| `ssos-headless.launch.py` | dynamic `remappings` or overlay launch |
| `ssos-eclss-headless.sh` | pass manifest / `SSOS_LAUNCH_REMAPS` to launch |

---

## BL-004: SSOS ECLSS loop — follow-ups { #bl-004 }

**Status**: Not started  
**Related**: [ssos_eclss_loop_connection_plan.md](ssos_eclss_loop_connection_plan.md) (Phase 0–7 complete)

| Priority | Item | Description |
|----------|------|-------------|
| P1 | **ros2 E2E pytest (optional)** | SSOS container CI or live skip integration test |
| P1 | **LLM connection preflight** | Early fail with `OllamaClient.check_connection()` at llm mode start |
| P2 | **WRS in scenario team** | **Done.** `SsosEclssLoopTeam` issues `water_recovery` in labeled and LLM modes. `LoopMockEclssBackend.send_water_recovery_goal` still raises `NotImplementedError` (use `plant_sim` / `ros2`). |
| P2 | **Single ros2 scenario: ECLSS + EPS** | Power crisis and ECLSS in one run (`eclss.backend=ros2` + `eps.backend=ssos_eps`) |
| P2 | **rclpy native ECLSS client** | Migrate from CLI bridge (latency, CI stability) |
| P3 | **MkDocs CI deploy** | `docs/ssos-mkdocs` branch |
| P3 | **upstream CO₂ scrubber** | SSOS ECLSS extension → new Mock scenario |

### Edge cases (low priority — noted in 7d, not implemented)

| Item | Note |
|------|------|
| `co2_critical` unused (labeled) | ~~health evaluates critical but labeled rules only use `co2_high`~~ → **fixed (T3)**: escalate ARS when critical band is breached |
| One Piece provenance heuristic | operational events depend on message parsing |
| labeled ignores command failure | not reflected in next-step rule branching |
| `set_parameter` arbitrary path | allowlist recommended for production SSOS |

---

## BL-006: SSOS run reproducibility and dashboard enrichment (out of CLI v3 scope) { #bl-006 }

**Status**: Not started (after CLI v3 mounts + `ea run`)  
**Related**: [CLI guide](../../../../en/users/reference/cli.md), [scenario-ssos-eclss-loop.md](../../../../en/users/scenarios/ssos_eclss_loop/index.md)

CLI v3 focuses on **host one-command runs and results mounts**. The items below belong to the simulation/visualization layer.

### P1 — Plant initial state (ros2 vs mock)

| Item | Description |
| --- | --- |
| `scenario.yaml` | Mock defaults use teaching-scale kg (`initial_co2_storage_kg: 1.5`; see `thresholds`) |
| ros2 step 0 | Record `/co2_storage` after headless restart as `summary.plant_initial_co2_storage_kg` |
| Validation | Fail fast if outside tolerance vs scenario target (point to SSOS launch params) |
| SSOS side | Investigate launch params if headless default disagrees with expected plant state |

**Intent**: Run-to-run reset is handled by CLI (headless restart). Align ros2 plant telemetry (grams on wire) with scenario thresholds via bridge conversion — not tonne-scale mock literals.

### P2 — Streamlit dashboard (rich SSOS views)

Target: `src/tools/dashboard/ssos_views.py`, `app.py` — duration, threshold lines, ops/messages, compare, deep link (see Japanese BL-006 for detail).

---

## BL-007: SSOS ↔ EA time and step synchronization (next integration phase) { #bl-007 }

**Status**: Under consideration (separate from CLI v3 / Phase 8)  
**Related**: [scenario-ssos-eclss-loop.md](../../../../en/users/scenarios/ssos_eclss_loop/index.md), [ssos_eclss_physical_phenomena_overview.md](../investigations/ssos_eclss_physical_phenomena_overview.md), BL-004 (WRS mock), BL-006 (run-boundary reproducibility)

### Background

- **EA `steps`** are decision cycles (observe → deliberate → act). The **SSOS ros2 plant** advances continuously on wall clock.
- Only `LoopMockEclssBackend` guarantees **1 EA step = 1 physics tick** via `advance_step()`.
- `ea run` headless restart resets state **between runs**, not **between steps** inside a run.
- Current SSOS headless has **no global time_scale / sim clock** ([space_station_os](https://github.com/space-station-os/space_station_os)).

**Conclusion (for now)**: Strict 1:1 mapping between EA steps and SSOS physics time is **likely too hard**. Capture options in backlog for the next integration phase (**not in cli_v3_plan**).

### Current coupling model (keep)

| backend | Meaning of step | Use |
| --- | --- | --- |
| `mock` | Explicit tick (`mock_dynamics`) | Agents, thresholds, LLM comparison, pytest |
| `ros2` | Instant snapshot + wait for Action completion | SSOS smoke, E2E, demos (few steps) |

### Option A — Expand SSOS mock inside engineering_agents (preferred first candidate)

Build an **integrated SSOS-equivalent mock** in this repo: topic semantics, WRS/OGS/ARS dynamics, EPS coupling under EA-controlled ticks.

| Item | Contents |
| --- | --- |
| Scope | Extend `LoopMockEclssBackend` or add `SsosPlantMock`; align with `eclss_topics.py` |
| WRS / OGS | Step-synced Action/Service effects on mock (links to BL-004 WRS team) |
| EPS | Drive with existing `MockEpsBackend` / `EpsStack` on same tick |
| Pros | No upstream dependency; fast pytest; **step = physics tick** by design |
| Cons | Drift from real SSOS; need contract tests for topics and Action types |

### Option B — Upstream SSOS sim clock / tick sync

Fork/clone [space_station_os](https://github.com/space-station-os/space_station_os) and add **upstream changes**: `use_sim_time` + `/clock`, or pause physics until EA ticks.

| Item | Contents |
| --- | --- |
| Scope | Headless launch, node timers, Crew/metabolism drivers |
| Pros | Closer to real plant with possible step sync |
| Cons | High cost; maintenance burden; **may be overkill** for Mac Docker + real-time ops |

### Option C — Mitigation only (short term; overlaps BL-006)

No strict sync; strengthen **observation contract**:

- Timestamps on telemetry; optional `step_dwell_s` after Actions
- Step-0 plant validation (BL-006)
- Dashboard: wall time vs step

### Open questions (unscheduled)

1. Primary axis for next integration phase: A, B, C, or hybrid (**logic on A, ros2 smoke on few steps**)
2. Option A boundary: same `EclssBackend` Protocol as `Ros2EclssBridge`?
3. Minimal upstream API if pursuing B (`tick(Δt)`, pause, sim clock)
4. Explicit `simulation.ssos_time_model: mock_tick | ros2_snapshot` in `scenario.yaml`?

### Relation to other backlog items

| BL | Relation |
| --- | --- |
| BL-004 | WRS team, ECLSS+EPS unified scenario — overlaps Option A |
| BL-006 | Run-boundary reproducibility, step-0 check — Option C; not step sync |
| BL-003 | Launch remap — independent |

### Relation to development plan

- **Not** in the next implementation priority list (provenance, Phase 8, etc.)
- Tracked under **“SSOS integration — next phase”** in [development-plan.md](../../../../en/developers/development/index.md)
