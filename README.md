# Engineering Agents — a closed design loop for a life-support system

[日本語 README](README.ja.md) · [Docs](docs/en/index.md) · [Experiment record](docs/en/results.md) · [Agent design](docs/en/agent-design.md) · [Implementation specs](docs/en/specs/index.md)

Fifty agents live in a space habitat whose air, oxygen and water plant **is not big enough to keep them alive**. They operate it anyway, step by step, from raw telemetry. When the run ends — usually with a body count — a design agent reads the wreckage, sizes a bigger plant, verifies it by re-simulating, and hands its design to the next run as actual hardware.

Then it happens again. Fifty times.

That last part is the point. **The design loop closes.** What the agent proposes becomes the world the next generation of agents has to live in, so a bad design is not a low score — it is fifty deaths, thirty rounds later, in a run nobody has started yet.

```
telemetry → 50 operators decide → plant advances → crew lives or dies
    ↓
run artifacts → design agent → candidate → re-simulate → physics audit → score
    ↓
proposal becomes the next run's hardware  ─────────────────────────┐
    ↑                                                              │
    └──────────────────────────────────────────────────────────────┘
```

---

## Why this world

Not a generic multi-agent sandbox with a space skin. The physics, the numbers and the failure mode are all borrowed from real life-support engineering:

- **The plant is a mass balance, not a score.** Crew metabolism uses NASA **BVAD** rates (1.04 kg CO₂, 0.84 kg O₂, 2.28 kg water per person per day). Oxygen generation consumes water stoichiometrically at 1.126 kg/kg. Sabatier consumes captured CO₂. Nothing is created. [`plant_sim/model.py`](src/environment/ssos/eclss/plant_sim/model.py)
- **The backend can be a real robot stack.** `--backend ros2` drives a live [Space Station OS](https://github.com/space-station-os/space_station_os) instance in Docker over ROS 2 actions, services and topics. Same agents, same code path, different plant.
- **Designs cost money and mass.** Every candidate is priced through an affine rack model with a launch cost of 55 kUSD/kg — an exploration figure in the neighbourhood NASA OIG's CRS audits report (63.2–71.8 kUSD/kg). A design that keeps everyone alive but weighs 52 tonnes is a failure, and the system says so.
- **Occupants die.** Not a penalty term — a state change that removes agents from the roster. [`survival.py`](src/scenario/ssos_eclss_loop/survival.py)

The scenario is a real engineering question — *how much life support does a crew of fifty need, and what does it cost?* — with a real, checkable answer.

---

## The design that makes emergence possible

The world is specified to the decimal. The agents are told almost nothing about what to do with it.

**What an operator receives, per turn** ([`build_llm_situation`](src/scenario/agents/ssos_eclss_loop_team.py#L1001)):

```
step=17, co2_storage_kg=2.41, o2_storage_kg=5.88, product_water_reserve_l=61.2,
grey_water_collected_l=3.4, urine_buffer_l=6.1, captured_co2_kg=0.88,
ars_failure_enabled=False, ogs_failure_enabled=False, wrs_failure_enabled=False
```

plus four status words, tagged in the prompt itself as *"Descriptive assessment from the facility monitoring layer — **not a command**"*.

**What it is never given:**

| Not given | Why it matters |
| --- | --- |
| The threshold values | `co2_storage_high_kg: 2.0` drives the health words and the rule-base actor. The LLM sees `2.41` and the word `warning` and decides for itself |
| Any instruction to act | The contract's last line: *"Empty commands when you and teammates agree to hold this step."* Holding is a first-class outcome |
| A recommended command | The levers block says what each command **is** and what its fields **mean**. Nothing says which, or how much |
| The dose | Choosing `air_revitalisation` means choosing `initial_co2_mass` yourself. That number scales the machine |
| What teammates said this step | All fifty deliberate **simultaneously** against the previous step's discourse. Agreement forms across steps, or not at all |

The charter is one paragraph, and this is its operative sentence ([`persona.py:15`](src/core/agents/persona.py#L15)):

> Ground claims in Telemetry (numbers) and World state (descriptive health). **Normative safety judgment is yours as an ECLSS engineer — do not assume hidden facility thresholds.**

Personas are *ways of thinking* — first principles, systems, risk — deliberately free of scenario names, thresholds and action catalogues, so the same roster transfers to a scenario it has never seen.

Meanwhile the world enforces what the world enforces, whatever anyone believes: one command per subsystem per step, a busy machine refuses work for 4800 s, and fifty people produce 52 kg of CO₂ a day.

→ Full treatment: **[Agent design — what the world enforces, what the model decides](docs/en/agent-design.md)**

---

## The design agent, and what it is *not* allowed to do

The design side draws the line somewhere else, and the reason is an observed failure: when the model also chose which tool to call next, one run spent twenty-one turns re-checking the same constraint and produced one candidate in fifteen minutes.

```
LLM     = design judgement only
Python  = investigation, verification, simulation, evaluation, comparison, workflow
```

Each turn it gets one freshly assembled page and returns one of exactly two answers:

```json
{"decision": "propose_candidate", "rationale": "...", "fields": {"plant_sim.ars.capacity_kg_day": 20.8}}
{"decision": "finish",            "rationale": "...", "selected_candidate_id": "candidate_003"}
```

It never picks a tool. It never judges pass/fail. What it decides is the entire design — three continuous variables, anywhere in their engineering bounds, with no gradient and no optimiser.

Everything else runs in fixed order, in code, for every candidate: **nine deterministic tools, not one of which calls an LLM** ([`design_tools.py`](src/scenario/ssos_eclss_loop/design_tools.py)). All arithmetic that decides a design happens there, so a small model cannot hallucinate the numbers.

Because the loop closes, three specific dishonesties would be worth money — so each has a gate:

| Gate | Question | File |
| --- | --- | --- |
| **Evidence Gate** | Was this candidate actually re-simulated, and do the adopted fields come from *that run's record*? | [`ssos_tool_use_design.py`](src/scenario/agents/ssos_tool_use_design.py) |
| **Physics Gate** | Reading **telemetry alone**: inventories non-negative, totals monotonic, carbon/oxygen/water ledgers balanced. Nine checks | [`physics_gate.py`](src/scenario/ssos_eclss_loop/physics_gate.py) |
| **Integrity Guard** | Did this run move its own scoring bar, operating point, or fault schedule? | [`integrity_guard.py`](src/scenario/ssos_eclss_loop/integrity_guard.py) |

A run that fails the physics gate is **not scored at all** — the integrity guard refuses a score the run is not entitled to, rather than scoring it lower.

---

## Memory — three tiers, three different reasons

| Tier | What | Size | Why |
| --- | --- | --- | --- |
| **Private** | Per agent, within a run. Includes an optional `"memory"` field **the model writes itself** | 30 entries | Not a log dump — the agent chooses what is worth keeping |
| **Discourse** | Shared, within a run | 22 messages | *Less than one full 50-agent step.* You can cite recent teammates; you cannot read the room. Information has to propagate |
| **Chain** | Between runs: `compact_chain_memory.json` | **4096 bytes, hard cap** | Its only reader is a model with finite context. It is a note, not a history, and never grows with the round count |

Chain memory exists because of one measured disaster:

```
round 24: ARS=20.8, OGS=42.0, WRS=1.8  → 50/50 alive, score 66.18
round 25: a WRS-only proposal          → next run installs baseline → 0/50
```

The design that worked was not rejected. **It was forgotten.** Every round assembles its state fresh from its own run — which is what makes a round auditable, and is exactly why the chain had no memory. Chain memory carries four things and nothing else: the best full-survival design, what was *actually installed* last round, **where each subsystem was measured to stop keeping the crew alive**, and up to five ways this chain has already lost people. Over 4 KB it drops the least useful entry rather than truncating text.

Those limits are measured, not calculated, and the distinction cost a run to learn. A calculated minimum was asserted per subsystem and the designer was told not to cross it — so it became the answer: from the round the two gas subsystems first touched theirs, twenty further rounds moved neither. They are 91% of the mass. And one of the three figures was simply wrong. Now `floor_probe.py` grows the shipped machine until everyone comes back, then walks each subsystem down alone until occupants are lost — 34 simulations, 16 seconds, no model asked anything. What the designer sees is the two ends of each bracket:

```text
CO2 scrubber      20.79 kept everyone   20.45 lost 12
oxygen generator  42.04 kept everyone   41.35 lost  2
water recycler     1.98 kept everyone    1.95 lost  4
```

No threshold, no floor, no instruction. Someone shown that twelve occupants died at 20.45 does not need to be told 20.8 is a limit.

It also carries an exploration directive: four rounds *in the same survival tier* without a 0.25-point gain, and the next round is told, in words, that it is going in circles.

→ [Memory design in detail](docs/en/agent-design.md#4-memory)

---

## What actually happened

Four fifty-round chains, same world, same crew. Between them, three changes. Every figure below is read from the per-round metrics committed in [`docs/data/`](docs/data).

| | Phase 1 — as built | Phase 2 — + chain memory | Phase 3 — + re-anchored scorecard | Phase 4 — + audit panel |
| --- | ---: | ---: | ---: | ---: |
| **Final survivors** | **34/50** | **50/50** | **50/50** | **50/50** |
| Rounds at 0/50 | 12 | 1 | 1 | 1 |
| Complete design proposals | 38/50 | 50/50 | 50/50 | 50/50 |
| Unique designs explored | 39 | 11 | 17 | 9 |
| Best / mean score | 66.18 / 61.71 | 66.36 / 65.94 | 84.23 / 83.34 | 84.03 / 82.59 |

*Phase 3 and 4 scores are not comparable to 1–2 — the scoring function changed. Phase 4 uses the phase-3 sheet. Comparable across all four: survivors, resets, proposal completeness, unique designs.*

![Survivors and score across four phases](docs/images/results/ssos_phase1_phase2_phase3_survival_score_trend.svg)

Four findings worth the run time:

1. **Phase 1 was not a search failure — it was a state-inheritance failure.** It explored 39 unique designs, more than either later phase, and found a full-survival answer at round 24. It just could not hold on to it, and ended twenty-six rounds later, worse.
2. **A 4 KB note fixed it.** Twelve catastrophic resets became one. Every proposal thereafter named all three subsystems. The cost: unique designs fell from 39 to 11 as the search narrowed.
3. **The scorecard was measuring the wrong thing.** Full marks on cost and mass sat at the *shipped baseline*, which kills everyone — so every survivable design, being necessarily larger, was marked expensive. Two very different survivable designs scored 11.6 and 4.1 out of 40; the sheet could not tell them apart. Re-anchoring to the smallest observed survivable design fixed the resolution.
4. **The audit panel stopped the dangerous cut — and the search.** Phase 4 locked at `20.8 / 42.0 / 1.65` from round 17 and never visited phase 3's WRS=1.25 failure (45/50) or the 1.8–2.2 band that scored 84.23. Unique designs fell from 17 to 9.

And what is still wrong, stated in the same place: total mass and cost did **not** improve much between phases 2, 3, and 4 — the score moved because the scoring moved. The search stayed on one axis, then froze. One model, one seed, four chains — not a statistical study.

Two of those have since been diagnosed and fixed (`0aaec84`), which is the fourth finding and the most uncomfortable one. The chain was handed a *calculated* minimum per subsystem and told not to cross it — so it stopped there: from the round the two gas subsystems first touched theirs, twenty further rounds moved neither, and they are 91% of the mass. One of the three figures was also wrong. **The floor is measured now** — grow the machine until everyone comes back, walk each subsystem down alone until they do not, show the designer both ends and no threshold. And the resets themselves turned out to be a plumbing bug: a proposal was merged into the scenario file rather than the machine the run was flying, so naming one subsystem reverted the other two. Whether the search spreads now that nothing forbids going lower is **unmeasured** — that is the next chain, not a claim.

→ **[Full experiment record](docs/en/results.md)**

### Every claim above is re-derivable

The whole chain is in the repository, and the last step is a `diff`:

| | Where | Size |
| --- | --- | --- |
| **Run a chain** | [`scripts/run_design_chain.sh`](scripts/run_design_chain.sh) · [`.ps1`](scripts/windows/run_design_chain.ps1) | |
| **Raw logs** — all four chains, whole | [`experiments/runs/*.tar.gz`](experiments/runs) | 43 MB (115 MB each extracted) |
| **Analysis scripts** — stdlib only, no numpy | [`experiments/analysis/`](experiments/analysis) | 6 scripts |
| **Analysed data** — 50 rows × 54 columns per phase | [`docs/data/`](docs/data) | |
| **Figures** | [`docs/images/results/`](docs/images/results) | |

```bash
cd experiments
for f in runs/*.tar.gz; do tar -xzf "$f" -C runs/; done
python3 analysis/analyze_ssos_iter.py --root runs/phase3-rescored --prefix phase3
diff outputs/phase3_iteration_metrics.csv ../docs/data/phase3_iteration_metrics.csv   # empty
```

The raw logs keep everything: `tool_trace.jsonl` has the real arguments and return values of all nine tools, `design_decision_state.json` has the model's reply verbatim, and `candidate_runs/` has the re-simulation of every candidate it named. A design can be walked back from the telemetry it was based on to the sentence that proposed it. → [`experiments/README.md`](experiments/README.md)

---

## Quick start

**You need:** Python 3.11+ and Git. Docker only for `--backend ros2`. Ollama or vLLM only for `--agents-mode llm`.

```bash
git clone https://github.com/hirototamura/engineering_agents.git
cd engineering_agents
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip && pip install -e ".[dev]"
ea doctor
```

<details>
<summary>Windows PowerShell</summary>

```powershell
git clone https://github.com/hirototamura/engineering_agents.git
cd engineering_agents
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m tools.cli doctor
```

For SSOS live runs install [Docker Desktop](https://www.docker.com/products/docker-desktop/) with the **WSL 2** backend and run `scripts/*.sh` from Git Bash. Full walkthrough: [docs/en/overview.md §2B](docs/en/overview.md#2b-windows-powershell--docker-desktop).
</details>

**Run something — no Docker, no LLM:**

```bash
ea run ssos_eclss_loop --backend plant_sim --agents-mode labeled_rule_base --steps 40
ea results
```

**Run the design loop** (needs an LLM; Ollama is enough):

```bash
ea run ssos_eclss_loop --iterate 10 --llm-provider ollama --llm-model qwen3:8b
```

**Look at it:**

```bash
python3 -m streamlit run src/tools/dashboard/app.py
```

<video src="https://github.com/user-attachments/assets/f2c778af-bd48-4188-98ca-00ce106a7b38" controls muted playsinline width="100%">
  <a href="https://github.com/user-attachments/assets/f2c778af-bd48-4188-98ca-00ce106a7b38">Download MP4</a>
</video>

| Command | Purpose |
| --- | --- |
| `ea run [SCENARIO]` | Run one simulation, or a chain with `--iterate N` |
| `ea scenarios` | List scenarios |
| `ea results [RUN_ID]` | Recent runs, or one `summary.json` |
| `ea doctor` | Check Python, deps, Docker/SSOS, Ollama, vLLM |

If `ea` is not on `PATH`, use `python3 -m tools.cli`.

### Scenarios

| Scenario | What it simulates |
| --- | --- |
| `ssos_eclss_loop` | 50 agents operating SSOS ECLSS (ARS/OGS/WRS), then a design agent sizing the next build |
| `scrubber_degradation` | CO₂ scrubber anomaly on a Python mock plant |

### Where results land

```
src/experiments/results/<run_id>/
├── telemetry.jsonl                 step-by-step plant metrics
├── messages.jsonl                  every agent utterance, reasoning, and captured thinking
├── design_decision_state.json      the page the model saw, and what it answered
├── design_proposals.json           the sizing handed to the next round
├── evaluation.json                 the scorecard, per axis, with points_lost
└── summary.json                    run metadata
```

Chains add `<chain>/NN/` per round, plus `compact_chain_memory.json` and `chain_summary.json`.

---

## Architecture

```
tools/cli          ea run / scenarios / results / doctor      Typer
   │
scenario/          per-scenario step loop, agents.yaml, scenario.yaml
   │               ssos_eclss_loop: design tools, gates, evaluation, chain memory
   │
core/              Scenario ABC · Team · persona/memory · LLMClient ABC · JSON parsing
   │
environment/       EclssBackend Protocol  ──  mock │ plant_sim │ ros2 (live SSOS)
```

Every seam is a swap, not a rewrite:

| Change | Cost |
| --- | --- |
| A different plant | one class satisfying a 9-method `Protocol` + one `if` branch. Three ship (arithmetic mock / mass-balance sim / live ROS 2) |
| A new scenario | one directory with a `scenario.yaml`. Discovered from the filesystem, not registered |
| Different agent behaviour | `mode: none │ labeled_rule_base │ llm` in YAML. Operator and designer sides are independent |
| Different world rules | `scenario.yaml`, or `--set plant_sim.crew.size=120` at the command line |
| A new design variable | one `CapacityVariable` entry + sizing coefficients. The loop, tools, gates and evaluation need no change — the model's contract is generated from the key list |

→ [Extending](docs/en/extending.md) · [Architecture](docs/en/architecture.md) · [API contracts](docs/en/api-contracts.md)

---

## Technical notes

**LLM integration.** Ollama and vLLM behind one `LLMClient` ABC. Provider, model, temperature and token budget are per-side config — the shipped setup runs a 9B for fifty operators and a 27B for the one designer, on different ports.

Self-hosted servers can't be relied on for native function calling, so the protocol is a plain JSON contract. [`core/llm/parsing.py`](src/core/llm/parsing.py) exists because of a specific 90-minute wasted run where *all 360 agent steps were parser fallbacks* and it read as a behaviour change. So parsing returns a status — `ok` / `partial` / `fallback` / `empty_response` — and `fallback` explicitly means *do not treat this as an agent decision*. `extract_json_block` takes the **last** balanced object (models that think then answer put the answer at the end); `strip_thinking_tags` handles `<think>`/`<thinking>`/`<thought>` including blocks left unclosed by `max_tokens` truncation.

Provider reasoning (vLLM `reasoning_content`, Ollama `thinking`) is merged with think-tag bodies and persisted. A design nobody can retrace is not reviewable.

**Failure handling.** Unreadable reply → one repair, charged to the same budget → deterministic fallback keeping every already-verified candidate. Budget exhaustion is a *normal* ending, not an error.

**Concurrency and reproducibility.** Fifty agents deliberate in one batch through a 128-worker pool with a loop-agnostic `threading.BoundedSemaphore` (an `asyncio.Semaphore` breaks on the next step's `asyncio.run`). Steps are synchronous: all agents observe the same snapshot, then the plant advances once. The simulator has no RNG — same config, same commands, same trajectory to the decimal, which is what lets a candidate's *predicted* outcome be checked against the next round's *measured* one.

**Tests.** 849 passing, 4 skipped.

```bash
pytest tests --ignore=tests/e2e
```

Not smoke tests — they test the adversarial cases. `test_ssos_physics_gate.py` (244 lines) feeds the audit doctored telemetry: `test_broken_mass_balance_fails`, `test_negative_inventory_fails`, `test_stoichiometry_violation_fails`, `test_failed_subsystem_that_processed_work_fails`, `test_processing_beyond_installed_capacity_fails`. `test_chain_final_answer.py` (313) pins down what a chain may answer with: `test_a_design_that_loses_occupants_is_never_the_answer`, `test_an_unaudited_design_is_never_the_answer`, `test_a_threshold_that_moves_partway_through_stops_the_ranking`, `test_nothing_found_is_reported_as_nothing_found`. `test_ssos_chain_memory.py` (651) covers the 4 KB budget, eviction order and stagnation detection.

---

## Roadmap

Each item is something the three chains **measured** as missing.

- **P0** — regression-test the chain memory mechanism. It removed eleven of twelve catastrophic resets and nothing currently fails if it stops working.
- **P1** — run a fourth chain now that the asserted floor is gone, and check whether the search actually spreads past the water recycler. Unmeasured, and the interesting question.
- **P1** — print new score, old score recomputed, total M$, total kg and survivors side by side, so "the scoring changed" can never again read as "the design improved".
- **P2** — a safety floor during exploration (round 34 cost five lives); prune volume and `over_budget` from the decision page; show candidate id and applied round together.

Further out: a review board instead of one designer; an LLM crew under an LLM designer; ECLSS sized against the EPS power budget (the ROS 2 bridge already exists); design variables that aren't capacities. And beyond a habitat — the machinery is not ECLSS-specific, but the physics model is the part that doesn't transfer for free, and without one the whole thing is a chat log.

→ [Full roadmap](docs/en/roadmap.md)

---

## How this was built

Every non-trivial change was specified first, implemented against the spec, then checked against its own acceptance criteria. Those specs are archived **verbatim**, including the parts that were later superseded, because the loop has been rebuilt three times and the current shape is unreadable without them.

| Spec | Decided | Status |
| --- | --- | --- |
| [Tool-use design agent redesign](docs/ja/specs/2026-08-28-tool-use-design-agent-redesign.md) | fetch your own evidence; verify by re-simulation | §10 superseded ↓ |
| [Design decision loop](docs/ja/specs/2026-08-29-design-decision-loop.md) | take *procedure* away from the LLM; gates | implemented |
| [Chain memory](docs/ja/specs/2026-08-30-chain-memory.md) | one 4 KB note between rounds | implemented |
| [Scoring & stagnation exploration](docs/ja/specs/2026-08-30-scoring-and-stagnation-exploration.md) | re-anchor cost/mass; detect circling | implemented |

→ [Spec index, with spec-section → source-file mapping](docs/en/specs/index.md)

---

## Documentation

| | English | 日本語 |
| --- | --- | --- |
| Quick start | [docs/en/index.md](docs/en/index.md) | [docs/ja/index.md](docs/ja/index.md) |
| Overview | [docs/en/overview.md](docs/en/overview.md) | [docs/ja/overview.md](docs/ja/overview.md) |
| **Agent design** | [agent-design.md](docs/en/agent-design.md) | [agent-design.md](docs/ja/agent-design.md) |
| **Experiment record** | [results.md](docs/en/results.md) | [results.md](docs/ja/results.md) |
| **Extending** | [extending.md](docs/en/extending.md) | [extending.md](docs/ja/extending.md) |
| **Roadmap** | [roadmap.md](docs/en/roadmap.md) | [roadmap.md](docs/ja/roadmap.md) |
| **Implementation specs** | [specs/index.md](docs/en/specs/index.md) | [specs/index.md](docs/ja/specs/index.md) |
| Architecture | [architecture.md](docs/en/architecture.md) | [architecture.md](docs/ja/architecture.md) |
| API contracts | [api-contracts.md](docs/en/api-contracts.md) | [api-contracts.md](docs/ja/api-contracts.md) |
| CLI guide | [cli.md](docs/en/cli.md) | [cli.md](docs/ja/cli.md) |
| Design agent (in depth) | [tool_use_design_agent.md](docs/en/memo/ssos_eclss_loop/tool_use_design_agent.md) | [tool_use_design_agent.md](docs/ja/memo/ssos_eclss_loop/tool_use_design_agent.md) |
| SSOS integration | [ssos/index.md](docs/en/ssos/index.md) | [ssos/index.md](docs/ja/ssos/index.md) |
| Engineering guide | [AGENTS.md](docs/en/AGENTS.md) | [AGENTS.md](docs/ja/AGENTS.md) |

```bash
pip install -e ".[dev]" && mkdocs serve   # → http://127.0.0.1:8000/  ·  /ja/
```

---

## License

[Apache License 2.0](LICENSE.txt) — Copyright 2026 One Piece Engineering
