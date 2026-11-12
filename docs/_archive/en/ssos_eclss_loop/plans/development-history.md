# Development history

Historical development plans and progress. CLI v3 is now available. Test counts and scheduled work below are historical; see the [scenario parent](../../../../en/users/scenarios/ssos_eclss_loop/index.md) and [evaluation](../../../../en/developers/scenarios/ssos_eclss_loop/evaluation.md) for current behavior.

### ssos_eclss_loop (SSOS live ECLSS) — Phase 0–7 complete

| Phase | Contents | Status |
| --- | --- | --- |
| 0 | Remove runtime `DesignChange` | ✅ |
| 1a–1b | ARS/OGS smoke, `EclssBackend`, `Ros2EclssBridge` | ✅ |
| 2 | WRS bridge | ✅ |
| 4 | `ssos_eclss_loop` + `SsosEclssLoopTeam` | ✅ |
| 5 | `design_proposals.json` (`ssos_graph`) + `--apply-proposals` | ✅ |
| 6 | LLM agents + Docker `ea-loop` (ros2 / Ollama defaults) | ✅ |
| 7 | Client `graph_rewire`, `Team` ABC, ssos dashboard views | ✅ |
| 8 | ROS launch remap + gateway | 📋 [backlog BL-003](backlog.md#bl-003) |

**Tests**: `pytest --ignore=tests/e2e` — **205 passed**, 4 skipped (ROS2 live / outside container tests skip).

**Container regression**: `./scripts/run_ssos_regression.sh` (Tier 1 pytest; `SSOS_E2E=1` for Tier 2 smoke chain). CI: `.github/workflows/ssos-e2e.yml`.

**Time model (current)**: `mock` — 1 EA step = 1 physics tick. `ros2` — SSOS wall-clock snapshots (no step sync). Run-to-run reset via headless restart. Step-sync strategy: [BL-007](backlog.md#bl-007).

**Container runs (target)**: `scripts/ssos/mac/ssos-run-detached.sh` (src + results + helper mounts) → host `ea run ssos_eclss_loop` only. Headless restart is handled by internal CLI bash.

---

## In progress

| Item | Description | Reference |
| --- | --- | --- |
| **CLI v3 — SSOS one command from host** | Volume mounts + `ea run ssos_eclss_loop` (internal bash), `duration_wall_s`, rclpy shutdown, `ea results` | [cli.md](../../../../en/users/reference/cli.md) |
| LLM comparison experiments | Trajectory comparison across models, temperature, run_id (dashboard compare) | [architecture.md](../../../../en/developers/architecture.md) |
| Documentation | Keep `docs/ja/` and `docs/en/` in sync with code and memos | [MAINTENANCE.md](../../../../en/developers/development/documentation.md) |

**Out of CLI v3 scope** (backlog): ros2 plant initial-state validation vs scenario kg thresholds, rich SSOS Streamlit views — [BL-006](backlog.md#bl-006)

**Next integration phase (under consideration)**: EA step vs SSOS physics time — expanded mock vs upstream sim clock — [BL-007](backlog.md#bl-007) (separate from CLI v3 / Phase 8)

---

## Next implementation (priority order)

1. **provenance extension** — export scrubber / ssos `design_proposals.json` to One Piece records
2. **provenance index** — cross-run `provenance_index.json`
3. **Phase 8 — ROS launch remap** — apply `graph_rewire` at launch (BL-003)
4. **Single ros2 scenario: ECLSS + EPS** — power crisis and SSOS ECLSS in one run (BL-004)
5. **EPS 3b/3c** — direct BCDU discharge, `/bcdu/operation` Action (BL-005)

---

## Later (near out of scope)

| Item | Status | Reference |
| --- | --- | --- |
| One Piece Web / SSOT UI | Not connected (JSON provenance only) | [one-piece-integration.md](../../../../en/developers/records-integrations.md) |
| `agents.mode: base` | Not implemented (emergent roles) | [backlog.md](../../../../en/developers/index.md) BL-001 |
| Evolving persona research | Backlog | BL-002 |
| WRS in `SsosEclssLoopTeam` | **Shipped** — labeled/llm issue `water_recovery`; LoopMock still raises | `ssos_eclss_loop_team.py` |
| MkDocs CI deploy | `docs/ssos-mkdocs` branch | BL-004 |
| SSOS ↔ EA step sync | Under consideration (mock vs upstream) | [BL-007](backlog.md#bl-007) |

---

## Roadmap (timeline)

```text
[Complete — scrubber MVP]
  Day 1–6   Layer separation, scrubber_degradation, dashboard
  EPS-1–4   SARJ/BCDU mock, StationSimulator, eps_telemetry
  Homogeneous N-agent LLM team

[Complete — SSOS integration Phase 0–7]
  1a–2     EclssBackend, ARS/OGS/WRS, Ros2EclssBridge
  3        Ros2EpsBridge (scrubber power)
  4–6      ssos_eclss_loop, design_proposals, LLM, ea-loop
  7        client graph_rewire, Team ABC, ssos dashboard

[Next]
  Day 8–9  CLI, provenance index, design export
  Phase 8  launch remap + gateway (BL-003)
  BL-004/5 ECLSS+EPS unified scenario, EPS 3b/3c (WRS team shipped)

[Consideration — SSOS integration next phase]
  BL-007   EA step ↔ SSOS physics time (expanded mock A / upstream B / mitigation C)

[Research]
  BL-001   base mode (emergent roles)
  BL-002   evolving persona
```

Details: [memo/scrubber_degradation/mvp_plan.md](../../scrubber_degradation/plans/mvp_plan.md), [memo/ssos_eclss_loop/](../../../../en/users/scenarios/ssos_eclss_loop/index.md), [memo/backlog.md](../../../../en/developers/index.md).

---

## Research notes (`docs/en/memo/`)

| Memo | Contents |
| --- | --- |
| [ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](ssos_eclss_loop_connection_plan.md) | SSOS ECLSS Phase 0–7 details and verification steps |
| [ssos_eclss_loop/labeled_rule_base.md](../investigations/labeled_rule_base.md) | In-sim labeled ops: sized ARS/OGS/WRS, then cap |
| [ssos_eclss_loop/post_run_design_agent.md](../investigations/post_run_design_agent.md) | Actor / designer split; unbounded post-run `changes` |
| [ssos_eclss_loop/ssos_eps_ros2_connection_plan.md](../../scrubber_degradation/plans/ssos_eps_ros2_connection_plan.md) | EPS ROS2 bridge (Phase 3) |
| [ssos_eclss_loop/ssos_ros2_graph_design_investigation.md](../investigations/ssos_ros2_graph_design_investigation.md) | Gateway and remap investigation |
| [backlog.md](../../../../en/developers/index.md) | BL-001–BL-007 (emergent roles, Phase 8, ECLSS/EPS, CLI v3 out-of-scope, step-sync consideration) |
| [agents/homogeneous_agent_team_plan.md](../../agents/homogeneous_agent_team_plan.md) | Homogeneous N-agent team design |

---

## SSOS / One Piece integration (current state)

```text
[ ssos_eclss_loop — Phase 0–7 complete ]
  EclssBackend (mock | ros2) → SsosEclssLoopTeam(Team)
       ↓ JSONL + design_proposals.json (ssos_graph)
  Dashboard (storage kg / operational timeline)
  ea-loop (Docker) + graph_rewire (client remap)

[ Not connected / backlog ]
  ROS launch remap (Phase 8)     … BL-003
  design_proposals → provenance  … Day 9
  EA step ↔ SSOS physics sync    … BL-007 (under consideration)
  One Piece Web UI               … out of scope
```

One Piece integration: [one-piece-integration.md](../../../../en/developers/records-integrations.md).

---

## Contributor checklist

When adding a feature:

1. If you change `SimulatorProtocol` / `EclssBackend` / JSONL schema, update [api-contracts.md](../../../../en/developers/reference/execution.md)
2. If you add agents or scenarios, update [architecture.md](../../../../en/developers/architecture.md)
3. Regression: `pytest` (full suite); scrubber: `test_scrubber_baseline.py` / `test_scrubber_with_agents.py`; ssos: `test_ssos_eclss_loop*.py`
4. SSOS container verification: `./scripts/run_ssos_eclss_loop.sh`, `run_graph_rewire_e2e.sh` (requires ECLSS headless)
5. Move completed items to “Complete” in this file; manage backlog in [backlog.md](../../../../en/developers/index.md)
