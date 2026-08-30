# Implementation specs (archive)

Every non-trivial change to the design agent was written down as a spec first, implemented against it, and then checked against its own acceptance criteria. Those specs are kept here **verbatim, in the Japanese they were written in** — not rewritten, not tidied up, not corrected after the fact.

They are kept because this repository's centre is a recursive loop — an agent proposes a design, the design is simulated, the result feeds the next proposal — and that loop has been rebuilt three times. Without the specs, the current shape of the code is unreadable: you can see *what* it does but not *what broke* to make it that way.

Each spec follows the same order: background → non-goals → files touched → schema → acceptance criteria → implementation steps. The acceptance-criteria section is close to a literal transcript of the tests that were then written.

| # | Spec | Date | What it decided | Status |
| --- | --- | --- | --- | --- |
| 1 | [Tool-use design agent redesign](https://github.com/hirototamura/engineering_agents/blob/main/docs/ja/specs/2026-08-28-tool-use-design-agent-redesign.md) | 2026-08-28 | Turn the design agent from "read the summary, propose" into "fetch your own evidence, verify by re-simulation". Defines the design variables, the constraint model, the objective, and the per-step command limit | Implemented; §10 superseded by spec 2 |
| 2 | [Design decision loop](https://github.com/hirototamura/engineering_agents/blob/main/docs/ja/specs/2026-08-29-design-decision-loop.md) | 2026-08-29 | Take *procedure* away from the LLM. Decision loop, DesignState, automated candidate pipeline, scoring integrity guard, telemetry-only physics gate | Implemented |
| 3 | [Chain memory](https://github.com/hirototamura/engineering_agents/blob/main/docs/ja/specs/2026-08-30-chain-memory.md) | 2026-08-30 | One 4 KB note carried between rounds, after a fifty-round run forgot a design that had kept the whole crew alive | Implemented |
| 4 | [Scoring and stagnation exploration](https://github.com/hirototamura/engineering_agents/blob/main/docs/ja/specs/2026-08-30-scoring-and-stagnation-exploration.md) | 2026-08-30 | Move the full-marks line for cost and mass off the non-surviving baseline; tell the chain when it has stopped moving | Implemented |

---

## 1 — Tool-use design agent redesign (2026-08-28)

**Why.** The post-run designer read `summary.json` and a slice of state, then wrote `design_proposals.json`. None of what a human engineer actually does was there: go and fetch the information you need, read the time series, compute the theoretical requirement, verify a candidate by re-simulating it.

| Spec section | Code |
| --- | --- |
| §5 tool infrastructure, §5.2 registry | `src/scenario/ssos_eclss_loop/design_tools.py` — nine deterministic tools |
| §6 design-variable schema | `src/scenario/ssos_eclss_loop/design_variables.py` |
| §7 one command per subsystem per step, §7.1 busy guard | `src/scenario/agents/ssos_eclss_loop_team.py`, `src/environment/ssos/eclss/plant_sim/model.py` |
| §8 constraint model (`rack_affine_linear_v1`) | `src/scenario/ssos_eclss_loop/design_constraints.py`, `scenario.yaml` `design_constraints:` |
| §9 objective | `src/scenario/ssos_eclss_loop/design_eval.py` |
| §12 candidate re-simulation | `design_tools.py` `run_design_candidate` |

Commits: `bee61ba` `33c7722` `beb96d6` `6cf8ac7` `8c59d78` `dac8bf1`

**Superseded part.** §10, the autonomous planning loop. An observed run spent twenty-one turns re-checking the same constraint and finished with one candidate in fifteen minutes, because nothing in the loop obliged the model to move on. Spec 2 replaces that section outright.

## 2 — Design decision loop (2026-08-29)

**Why.** Spec 1 asked the model both *what to design* and *how to run the review*. Give it the procedure and nothing pushes the loop forward.

**The split it fixed:** `LLM = design judgement only`. `Python = investigation, verification, simulation, evaluation, comparison, workflow`. The model is handed one freshly assembled page and answers one of two things: try this sizing, or finish.

| Spec section | Code |
| --- | --- |
| §5 decision loop | `src/scenario/agents/ssos_tool_use_design.py` |
| §6 DesignState | `src/scenario/ssos_eclss_loop/design_state.py` |
| §7 candidate pipeline | `ssos_tool_use_design.py` — eight tools in fixed order, every candidate |
| §8 call budget, §9 parse failure | `agents.yaml` `design.tool_use.decision_loop`, `src/core/llm/parsing.py` |
| §11 scoring integrity guard | `src/scenario/ssos_eclss_loop/integrity_guard.py` |
| §12 telemetry-only physics gate | `src/scenario/ssos_eclss_loop/physics_gate.py` |
| §13 telemetry additions | `src/environment/ssos/eclss/plant_sim/backend.py` |
| §14 evaluator integration | `src/scenario/ssos_eclss_loop/unified_evaluation.py` |
| §15 ranking | `design_eval.py` `rank_candidates` / `rank_rationale` |

Commits: `21681b7` `09756bd` `9befbb9` `34b5306` `c331d42` `8dd7944` `67f3bd0` `b828332`

**Added after the spec:** one answer for a whole chain (`chain_selection.py`, `67f3bd0`). Each round had a winner; nothing said how fifty rounds become one design.

## 3 — Chain memory (2026-08-30)

**Why.** A fifty-round run was analysed tool call by tool call. Inside one round the evidence was complete. Between rounds, nothing survived:

```
iteration 24: ARS=20.8, OGS=42.0, WRS=1.8  → 50/50 alive, score 66.18
iteration 25: a WRS-centred partial proposal
             → next run installs ARS=4.5, OGS=9.25 → 0/50
```

The design that worked was not rejected. It was forgotten.

**What was built.** One file at the root of a chain, `compact_chain_memory.json`, capped at 4 KB: the best design that kept everyone alive, the sizing actually installed last round, a calculated floor under each subsystem (measured, since `0aaec84`), and the handful of ways this chain has already lost the crew. Its only reader is a language model with a finite context window, so the size cap is a design constraint, not an implementation detail.

| Spec section | Code |
| --- | --- |
| schema, size cap, update logic | `src/scenario/ssos_eclss_loop/chain_memory.py` |
| `load_run_artifacts` addition | `design_tools.py` → `chain_memory_compact` |
| prompt addition | `design_state.py` `build_design_state` → `chain_memory` on the decision page |
| when it is written | `src/scenario/jobs/iterate.py` |

Commit: `c0dcb4f`

**Explicit non-goals, from the spec:** no vector DB, no raw telemetry in context, no redesign of the agent loop, no new optimiser.

**Left open by this spec, and closed later:** chain memory *showed*, it did not *apply* — a partial proposal still dropped the fields it omitted, and the spec said so rather than pretending otherwise. Showing it was enough to stop the collapse in practice (see the [experiment record](../results.md)); `0aaec84` then fixed the carrying itself, and replaced the calculated floor this spec introduced with a measured one.

## 4 — Scoring and stagnation exploration (2026-08-30)

**Why.** Spec 3 stopped the collapse. Two things were then visible:

1. Full marks on cost and mass sat at the **shipped baseline, which loses all fifty occupants**. Every survivable design is larger, so survivable designs scored 11.57/40 and 4.08/40 and the sheet could no longer tell two very different ones apart.
2. Score stopped moving while the search walked the same WRS neighbourhood.

| Spec section | Code |
| --- | --- |
| footprint scoring | `src/scenario/ssos_eclss_loop/evaluation.py`, `scenario.yaml` `evaluation.footprint` |
| pruning the designer-facing context | `design_state.py` — volume and `over_budget` no longer shown on their own |
| stagnation exploration | `chain_memory.py` `_detect_stagnation` / `_exploration_directive`, `scenario.yaml` `iteration.exploration` |
| survival tier | `chain_memory.py` `survival_tier` |

Commits: `d57ad2d` `4124475`

**Effect.** Cost and mass on a surviving design went from 5–6 points to 14; unique designs explored went from 11 to 17. Numbers in the [experiment record](../results.md).

---

## Where to start

If you are reading this for the first time, read [the design agent](../memo/ssos_eclss_loop/tool_use_design_agent.md) — what the code does now — before the specs. Come here when you want to know *why* it is shaped this way.

- The loop as it stands → [Design agent](../memo/ssos_eclss_loop/tool_use_design_agent.md)
- What actually happened when it ran → [Experiment record](../results.md)
- What the model is told and what it decides → [Agent design](../agent-design.md)
