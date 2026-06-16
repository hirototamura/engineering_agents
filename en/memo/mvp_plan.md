> Japanese: [../ja/memo/mvp_plan.md](../ja/memo/mvp_plan.md)

# ECLSS Resilience Loop — Directory Layout & 1-Week MVP Plan

> Design process record. Exported from Cursor plan `ECLSS Agent Directory MVP` (2026-05-30).  
> **Updated 2026-05-30**: Roadmap revised from Day 1–2 retrospective.  
> **Updated 2026-05-30**: Day 4 role design policy and research backlog ([backlog.md](backlog.md)) added.  
> **Updated 2026-05-31**: Day 5 reorganized to **LLM integration first (Day5A: labeled_shadow)**.  
> **Updated 2026-05-31**: Day5B completion reflected; Day6+ order replanned.  
> **Updated 2026-06-02**: ECLSS alone lacks power-margin recovery; next phase top priority is **EPS mock integration**.  
> **Updated 2026-06-02**: EPS day-by-day detail in [eps_implementation_plan.md](eps_implementation_plan.md).  
> **Updated 2026-06-02**: **EPS-1–4 complete** (`feature/eps-mock-foundation`). Next is Day 8 CLI.  
> **Updated 2026-06-02**: `labeled_shadow` mode removed (consolidated to `labeled` / `labeled_llm_guarded`).

## Goal

**Essence**: “Structured agent relationships” and “reliable API contract with the simulator” over high-fidelity physics.

**Current phase (Phase 1)**: On the ECLSS-oriented `src/` layers, keep **scrubber_degradation baseline scenario** always runnable while adding agents, UI, and design-change tracking.

### Premises (user confirmed)

- **Repo policy**: Existing bar sim moved to `src/materials/`. Under `src/`: `core`, `environment`, `experiments`, `scenario`, `scripts`, `tools`. At same level as `src`: `docs`, `memo`, `tests`.
- **SSOS integration**: Mock adapter first (ROS2 topic / command API compatible). Swap to real SSOS later.
- **Dev branches**: `feature/eclss-mvp` (ECLSS+agents PR merged) / EPS work on `feature/eps-mock-foundation`
- **Run prerequisite**: `pip install -e ".[dev]"` so `scenario` / `integrations` import (`integrations` is `src/integrations/`)

---

## Day 1–2 retrospective (complete)

| Item | Status | Notes |
| --- | --- | --- |
| `src/` layer split + materials move | ✅ | Day 1 |
| `core/` (sim loop, LLM, event_log) | ✅ | Day 1 ahead of schedule (old Day 3) |
| `SimulatorProtocol` + Mock ECLSS | ✅ | Day 2 |
| `telemetry.jsonl` / `health_metrics.jsonl` | ✅ | Day 2 |
| `docs/api-contracts.md` | ✅ | Day 2 |
| pytest 8 tests | ✅ | |

### Gaps found on Day 2 (resolved Day 3)

1. **scrubber_degradation not formalized as scenario** — logic hardcoded in `scripts/run_mock_eclss.py`.
2. **Demo narrative not established** — scrub exceeded production from start, CO2 monotonically decreased. Never reached danger zone (>1000 ppm).
3. **Missing baseline regression test** — no scenario-named guard test.

**Policy**: Keep architecture. Only reprioritize Day 3+ (no full plan rewrite).

---

## Revised 1-week MVP roadmap

| Day | Old plan | **Revised (adopted)** | Status |
| --- | --- | --- | --- |
| **1** | Directory migration + pyproject | Same | ✅ Done |
| **2** | Mock ECLSS + Protocol + telemetry | Same | ✅ Done |
| **3** | core extraction + runner skeleton | **scrubber_degradation formalized + runner + physics tuning + baseline regression** | ✅ Done |
| **4** | 4-role LLM agents | **scrubber_degradation-specific rule-based 4 roles** + recovery loop | ✅ Done |
| **5** | One Piece JSON provenance | **Day5A: LLM shadow integration** (`agents.mode: labeled_shadow`) → **Day5B: One Piece provenance** | ✅ Day5B done |
| **6** | Streamlit dashboard | Left chat + right CO2 chart (JSONL tail) + provenance step sync | ✅ Done |
| **7** | E2E + CLI | `tools.cli run --scenario scrubber_degradation` end-to-end | Not started |

### Day 1–5 retrospective (2026-05-31)

| Aspect | Status | Notes |
| --- | --- | --- |
| Baseline stability | ✅ | `agents.mode: none` maintained. Duplicate `anomaly_injected` fixed. |
| Agent integration | ✅ | `labeled` (rule) and `labeled_llm_guarded` (LLM + guard + fallback). |
| Shadow quality (removed) | — | Day5A `labeled_shadow` deleted 2026-06-02. History in Day 5A notes. |
| One Piece provenance | ✅ | Auto `provenance.jsonl`, `summary.provenance_*` added. |
| Incomplete | ⏳ | CLI / E2E / SSOS adapter contract (Day 8–10). EPS in [eps_implementation_plan.md](eps_implementation_plan.md). |

### Day 6+ implementation order (updated)

| Phase | Priority task | Done when |
| --- | --- | --- |
| **Day 6** | `tools/dashboard/app.py` (telemetry/health/messages/provenance together) | ✅ One screen: CO2 trend, role messages, design history with step sync |
| **Next-1 (Week-2 entry)** | SSOS EPS mock — [EPS-1–4](eps_implementation_plan.md#day-by-day-roadmap) | ✅ EPS-1–4 done |
| **Next-2** | CLI — [Day 8](eps_implementation_plan.md#day-8-cli-1-day) | One command runs baseline/labeled/labeled_llm_guarded + output paths |
| **Next-3** | One Piece extension — [Day 9](eps_implementation_plan.md#days-910-extensions) | Cross-run provenance aggregation; handoff spec to one-piece |
| **Next-4** | SSOS adapter early prep — [Day 10](eps_implementation_plan.md#days-910-extensions) | I/O contract and test stubs for `SsosAdapter` |

### Week-2 retrospective — EPS mock (2026-06-02, `feature/eps-mock-foundation`)

| Item | Status | Notes |
| --- | --- | --- |
| EPS-1 `request_eps_boost` | ✅ | Operator rule recovery path |
| EPS-2 SARJ + BCDU | ✅ | Thin mock + `test_mock_eps.py` |
| EPS-3 `StationSimulator` | ✅ | `summary.simulator: mock_station`; standalone ECLSS rejects boost |
| EPS-4 Observability | ✅ | `eps_telemetry.jsonl`, recovery provenance, dashboard SARJ/BCDU |
| Packaging | ✅ | `integrations` under `src/integrations/`, consistent import via `pip install -e` |

**Next**: Day 8 CLI → Day 9 provenance index → Day 10 SSOS adapter contract tests.

**Week-1 out of scope** (unchanged):

- Real SSOS / ROS2 runtime connection
- One Piece Web UI integration
- LLM required (deterministic baseline is primary)
- Batch sweep / video generation

---

## Demo scenario: `scrubber_degradation` (baseline)

**Critical**: **Baseline runnable without LLM** throughout Week-1. After changes, run `pytest tests/scenario/test_scrubber_baseline.py`.

- **Initial**: CO2 ≈ 800 ppm, scrubber efficiency 0.95
- **Step 20**: Compound anomaly — efficiency drop + power squeeze + CO2 production increase
- **Story**: Steps 1–19 near equilibrium → after step 20 CO2 **>1000 ppm** → Day 4+ recovery and design changes toward safe band
- **Baseline success**: 50 steps complete, step 20 anomaly, peak CO2 > 1000, logs written

### Day 4 — Agent role design policy

**Principle: Do not over-generalize. Start with scenario-specific roles.**

| Do | Do not (Week-1) |
| --- | --- |
| **Scenario-specific** 4 roles in `scrubber_degradation/agents.yaml` | Generic role framework for arbitrary scenarios |
| Monitor / Diagnostician / Operator / DesignEngineer **rule-based** | LLM required |
| `agents.mode: none \| labeled` (keep baseline) | `agents.mode: base` (emergent role experiment) |

Four roles are **provisional labels** to “dissolve” the anomaly. They mirror human division of labor; whether Base Role agents emerge situation-appropriate roles without labels is separate — tracked in **[backlog.md BL-001](backlog.md)**.

**Day 4 done when (labeled mode)**

- `messages.jsonl` structured messages from 4 roles
- Operator recovery commands → CO2 toward safe band
- DesignEngineer design change (bypass) in `design_state`
- `test_scrubber_baseline.py` green with `agents.mode: none`

### Day 5A — labeled_shadow quality notes (2026-05-31, mode removed 2026-06-02)

- `qwen3.5:2b` + relaxed prompt (JSON object only, multi-line allowed) improved `parse_status`
- 20-step trial (80 calls): **ok=79 / fallback=1 (1.25% fallback)**
- All fallbacks from `no balanced JSON object found` (JSON extraction failure)
- Fallback does not affect control (shadow log only). Day5B+ saves `parse_status` in provenance for audit

### Day 5B — One Piece provenance notes (2026-05-31)

- Added `integrations/one_piece/client.py`; auto `provenance.jsonl` at run end
- Join `events.jsonl` (design_change) + `messages.jsonl` + `design_state.jsonl`
- `summary.json`: `provenance_path` / `provenance_record_count`
- Baseline `provenance_record_count=0`; labeled / labeled_llm_guarded record design changes

### Next — EPS-first policy (2026-06-02)

Detailed roadmap: **[eps_implementation_plan.md](eps_implementation_plan.md)** (EPS-1 foundation → EPS-2 SARJ+BCDU → EPS-3 facade → EPS-4 observability → Day 8–10).

- Issue: ECLSS recovery commands alone cannot restore power margin; critical state hard to avoid
- Policy: Before One Piece/CLI extension, add EPS mock inspired by [space_station_eps](https://github.com/space-station-os/space_station_os/tree/main/space_station_eps) (thin mock, SARJ included)
- Implementation axes:
  - Add `request_eps_boost` to recovery path (EPS-1)
  - SARJ → BCDU → ECLSS coupling (EPS-2–3)
  - Visualize “rule vs LLM power recovery” in provenance / dashboard (EPS-4)

---

## Backlog (outside MVP · research)

Details in [backlog.md](backlog.md).

| ID | Theme | Summary |
| --- | --- | --- |
| **BL-001** | Labeled roles vs emergence | Labeled 4 roles vs Base Role (unlabeled) comparison |
| BL-002 | (Reserved) | — |

---

## Test policy

| Test | Purpose |
| --- | --- |
| `tests/environment/test_mock_eclss.py` | Mock unit |
| **`tests/scenario/test_scrubber_baseline.py`** | **Baseline end-to-end + story asserts (required every commit)** |

### Baseline asserts (Day 3)

1. `run_scenario("scrubber_degradation")` completes
2. `telemetry.jsonl` N lines + `health_metrics.jsonl` / `events.jsonl` / `summary.json` exist
3. After step 20 `anomaly_flags` includes `scrubber_degradation`
4. `peak_co2_ppm > 1000`

---

## Success criteria (MVP done)

1. `python -m tools.cli run --scenario scrubber_degradation` end-to-end — **not started (Day 8)**; interim: `run_scenario` / `run_mock_eclss.py`
2. Logs + `summary.json` — **7 streams** (incl. `eps_telemetry.jsonl`) + `provenance.jsonl` ✅
3. Streamlit step-sync UI (incl. EPS charts) ✅
4. Design changes + EPS recovery in `provenance.jsonl` ✅
5. **`pytest tests/scenario/test_scrubber_baseline.py` always green** ✅

---

## Implementation task list

- [x] src/ skeleton
- [x] Move existing bar sim to materials
- [x] SimulatorProtocol + JSONL schema
- [x] mock_eclss.py + ROS2-like topics
- [x] core generalization port
- [x] scrubber_degradation scenario.yaml + runner + baseline regression
- [x] Mock physics tuning (CO2 danger zone)
- [x] scrubber_degradation-specific rule-based 4 roles (agents.yaml, `mode: labeled_rule_base`)
- [ ] BL-001 emergent role experiment (`mode: base`) — backlog, outside Week-1
- [x] Day5A: LLM shadow (`agents.mode: labeled_shadow`, `decision_source`/`parse_status` logs)
- [x] Day5B: `src/integrations/one_piece/` provenance (`provenance.jsonl`, `summary.provenance_*`)
- [x] tools/dashboard/app.py (run select / step slider / telemetry+messages+events+provenance)
- [x] labeled_llm_guarded (Monitor/Diagnostician/Operator LLM; DesignEngineer guarded LLM)
- [x] EPS-1: `request_eps_boost` recovery (inline; facaded EPS-3) — [eps_implementation_plan.md](eps_implementation_plan.md)
- [x] EPS-2: `MockSarj` / `MockBcdu` / `EpsStack` + `test_mock_eps.py`
- [x] EPS-3: `StationSimulator` + runner `mock_station`
- [x] EPS-4: `eps_telemetry.jsonl` + recovery provenance + dashboard EPS panel
- [ ] tools/cli + scrubber_demo.yaml E2E (Day 8)

---

## References

- **EPS day-by-day plan**: [eps_implementation_plan.md](eps_implementation_plan.md)
- Doc index: [README.md](../README.md#documentation), dev plan: [docs/development-plan.md](../docs/development-plan.md)
- API contracts: [docs/api-contracts.md](../docs/api-contracts.md)
- Architecture: [docs/architecture.md](../docs/architecture.md)
- Scenario: [docs/scenario-scrubber-degradation.md](../docs/scenario-scrubber-degradation.md)
- One Piece: [docs/one-piece-integration.md](../docs/one-piece-integration.md)
