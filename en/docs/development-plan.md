> Japanese: [../../ja/docs/development-plan.md](../../ja/docs/development-plan.md)

# Development Plan (In Progress and Not Started)

This document aggregates **features not yet complete** and the **research backlog**. For available functionality, see [README.md](../README.md) and the scenario documents below.

| Document | Content |
| --- | --- |
| [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) | Mock scrubber narrative, configuration, outputs |
| [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md) | SSOS live ECLSS narrative, operations, Docker runs |
| [architecture.md](architecture.md) | Layer structure, dual-track execution flow |
| [api-contracts.md](api-contracts.md) | Protocols, JSONL schemas |

**SSOS integration Phase 0–7 status**: [memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](../memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md)

---

## Milestones

### scrubber_degradation (Mock ECLSS + EPS) — complete

| Area | Contents |
| --- | --- |
| Simulator | `StationSimulator` (`MockEclssSimulator` + `EpsBackend` mock / `ssos_eps`) |
| Scenario | `scrubber_degradation` — 50 steps, anomaly from step 20 |
| Agents | `none` / `labeled_rule_base` / `llm`, homogeneous N engineers |
| Recovery | Fan boost, load shed, EPS boost, temporary bypass |
| Post-run design | `design_proposals.json` (scrubber frozen; no runtime topology change) |
| provenance | Runtime **recovery** (`request_eps_boost`) |
| Dashboard | CO₂ ppm / EPS / topology / 2-run compare |

### ssos_eclss_loop (SSOS live ECLSS) — Phase 0–7 complete

| Phase | Contents | Status |
| --- | --- | --- |
| 0 | Remove runtime `DesignChange` | ✅ |
| 1a–1b | ARS/OGS smoke, `EclssBackend`, `Ros2EclssBridge` | ✅ |
| 2 | WRS bridge | ✅ |
| 3 | EPS coupling (scrubber path, `Ros2EpsBridge`) | ✅ |
| 4 | `ssos_eclss_loop` + `SsosEclssLoopTeam` | ✅ |
| 5 | `design_proposals.json` (`ssos_graph`) + `--apply-proposals` | ✅ |
| 6 | LLM agents + Docker `ea-loop` (ros2 / Ollama defaults) | ✅ |
| 7 | Client `graph_rewire`, `Team` ABC, ssos dashboard views | ✅ |
| 8 | ROS launch remap + gateway | 📋 [backlog BL-003](../memo/backlog.md#bl-003-ros-launch-remap-phase-8--graph_rewire-a) |

**Tests**: `pytest` — **140 passed**, 4 skipped (ROS2 live / outside container tests skip).

**Container runs**: `~/dev/ssos/ssos-run.sh` → `bash /root/ssos-eclss-headless.sh` → `./scripts/run_ssos_eclss_loop.sh` or `ea-loop` inside container.

---

## In progress

| Item | Description | Reference |
| --- | --- | --- |
| PR #9 merge and stabilization | `feat/ssos-eclss-loop` → `main` | connection plan |
| LLM comparison experiments | Trajectory comparison across models, temperature, run_id (dashboard compare) | [architecture.md](architecture.md) |
| Documentation | Sync `ja/docs/` and `en/docs/` with memo | this update |

---

## Next implementation (priority order)

1. **CLI integration** — single entry point such as `python -m tools.cli run --scenario …` ([memo/scrubber_degradation/eps_implementation_plan.md](../memo/scrubber_degradation/eps_implementation_plan.md) Day 8)
2. **provenance extension** — export scrubber / ssos `design_proposals.json` to One Piece records
3. **provenance index** — cross-run `provenance_index.json`
4. **Phase 8 — ROS launch remap** — apply `graph_rewire` at launch (BL-003)
5. **Single ros2 scenario: ECLSS + EPS** — power crisis and SSOS ECLSS in one run (BL-004)
6. **EPS 3b/3c** — direct BCDU discharge, `/bcdu/operation` Action (BL-005)

---

## Later (near out of scope)

| Item | Status | Reference |
| --- | --- | --- |
| One Piece Web / SSOT UI | Not connected (JSON provenance only) | [one-piece-integration.md](one-piece-integration.md) |
| `agents.mode: base` | Not implemented (emergent roles) | [backlog.md](../memo/backlog.md) BL-001 |
| Evolving persona research | Backlog | BL-002 |
| WRS in `SsosEclssLoopTeam` | Backlog | BL-004 |
| upstream CO₂ scrubber | Waiting on SSOS extension | BL-004 |
| MkDocs CI deploy | `docs/ssos-mkdocs` branch | BL-004 |

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
  BL-004/5 ECLSS+EPS unified scenario, EPS 3b/3c, WRS team

[Research]
  BL-001   base mode (emergent roles)
  BL-002   evolving persona
```

Details: [memo/scrubber_degradation/mvp_plan.md](../memo/scrubber_degradation/mvp_plan.md), [memo/ssos_eclss_loop/](../memo/ssos_eclss_loop/), [memo/backlog.md](../memo/backlog.md).

---

## Research notes (`en/memo/`)

| Memo | Contents |
| --- | --- |
| [mvp_plan.md](../memo/scrubber_degradation/mvp_plan.md) | Week roadmap, Day 1–10 |
| [ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](../memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) | SSOS ECLSS Phase 0–7 details and verification steps |
| [ssos_eclss_loop/ssos_eps_ros2_connection_plan.md](../memo/ssos_eclss_loop/ssos_eps_ros2_connection_plan.md) | EPS ROS2 bridge (Phase 3) |
| [ssos_eclss_loop/ssos_ros2_graph_design_investigation.md](../memo/ssos_eclss_loop/ssos_ros2_graph_design_investigation.md) | Gateway and remap investigation |
| [backlog.md](../memo/backlog.md) | BL-001–BL-005 (emergent roles, Phase 8, ECLSS/EPS follow-ups) |
| [agents/homogeneous_agent_team_plan.md](../memo/agents/homogeneous_agent_team_plan.md) | Homogeneous N-agent team design |
| [scrubber_degradation/eps_implementation_plan.md](../memo/scrubber_degradation/eps_implementation_plan.md) | EPS-1–4, CLI day boundaries |

---

## SSOS / One Piece integration (current state)

```text
[ scrubber_degradation — Mock frozen ]
  StationSimulator → ScrubberDegradationTeam
       ↓ JSONL + design_proposals.json (scrubber domain)
  Dashboard (ppm / EPS / topology)

[ ssos_eclss_loop — Phase 0–7 complete ]
  EclssBackend (mock | ros2) → SsosEclssLoopTeam(Team)
       ↓ JSONL + design_proposals.json (ssos_graph)
  Dashboard (storage kg / operational timeline)
  ea-loop (Docker) + graph_rewire (client remap)

[ Not connected / backlog ]
  ROS launch remap (Phase 8)     … BL-003
  design_proposals → provenance  … Day 9
  One Piece Web UI               … out of scope
```

One Piece integration: [one-piece-integration.md](one-piece-integration.md).

---

## Contributor checklist

When adding a feature:

1. If you change `SimulatorProtocol` / `EclssBackend` / JSONL schema, update [api-contracts.md](api-contracts.md)
2. If you add agents or scenarios, update [architecture.md](architecture.md)
3. Regression: `pytest` (full suite); scrubber: `test_scrubber_baseline.py` / `test_scrubber_with_agents.py`; ssos: `test_ssos_eclss_loop*.py`
4. SSOS container verification: `./scripts/run_ssos_eclss_loop.sh`, `run_graph_rewire_e2e.sh` (requires ECLSS headless)
5. Move completed items to “Complete” in this file; manage backlog in [backlog.md](../memo/backlog.md)
