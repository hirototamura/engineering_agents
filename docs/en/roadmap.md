# Roadmap

Priorities here are not wishes. Each one is something the [three fifty-round chains](results.md) measured as missing, and each names the file it lands in.

For SSOS/ROS 2 integration phases specifically, see [SSOS roadmap](ssos/roadmap.md).

---

## P0 — Lock in what has been measured to work

The chain memory mechanism removed eleven of twelve catastrophic resets. That result is now a regression risk: nothing in the test suite fails if the note stops reaching the designer.

| Task | Where | Acceptance |
| --- | --- | --- |
| Assert `chain_memory_compact` is in the tool-use context from round 2 onward | `tests/scenario/test_ssos_chain_memory.py` | a chain run with the note stripped fails |
| Assert the recorded best design names ARS **and** OGS **and** WRS | `chain_memory.py` `best_full_survival` | a two-field best is rejected |
| Assert a partial proposal does not reset the omitted fields to baseline | `design_proposals.py` | **done** in `0aaec84` — `complete_capacity_profile`, covered by `tests/scenario/test_ssos_design_proposals.py` |
| Keep an observed failure boundary as a bad pattern | `chain_memory.py` `known_bad_patterns` | WRS=1.25 → 45/50 survives into the next round's note |

## ~~P1 — Make chain memory *apply*, not only *show*~~ — done in `0aaec84`

A capacity proposal was merged into the *scenario file* rather than into the machine the run that produced it was flying, so naming one subsystem silently returned the other two to their shipped sizes. `complete_capacity_profile` now fills in whatever a proposal did not mention from what was actually installed. Nothing is overridden; an omission has simply stopped meaning "revert this".

The same commit replaced the *calculated* floor with a *measured* bracket (`floor_probe.py`), because the asserted minimum had become the answer: from the round the gas subsystems first touched it, twenty rounds moved neither, and one of the three figures was wrong.

**What this opens, and is the next thing to run:** ARS and OGS were pinned through most of phases 2 and 3 by that assertion. Nothing forbids going lower now. Whether the search actually spreads is unmeasured — a fourth chain answers it.

## P1 — Check that the search actually spreads

Phase 3's stagnation detector fired and asked for exploration, and the exploration it got was still WRS-only. The reason is now understood: ARS and OGS were held by an *asserted* minimum, and a line a designer may not cross becomes the answer. `0aaec84` removed the assertion and replaced it with a measured bracket. Nothing forbids going lower any more.

So the priority is no longer "add a rule that permits exploring" — it is **run a fourth chain and see**. What to look for:

| Question | What would answer it |
| --- | --- |
| Do ARS and OGS move at all now? | unique `config_ars` / `config_ogs` values per chain, against phase 3's one apiece |
| Does anything survive below the measured bracket? | rounds proposing under 20.79 / 42.04 / 1.98, and what came back |
| Does total mass or cost actually fall? | `total_mass_kg` and `total_cost_musd` at equal survival, not score |
| Does the recycler stop absorbing the whole search? | share of rounds whose only change is WRS |

If the search stays on one axis with nothing forbidding it, the cause is the directive text rather than the constraint, and that lands in `chain_memory.py` `_exploration_directive`.

## P1 — Separate "the scoring changed" from "the design improved"

Phase 3 scored 84 where phase 2 scored 66, and almost all of that is the scoring function, not the hardware. That confusion must not be possible again. Every future comparison prints five columns side by side:

```
new score | old score recomputed | total M$ | total kg | survivors
```

Lands in `evaluation.py` and the chain report in `tools/cli/output.py`.

## P2 — A safety floor during exploration

Round 34 dropped WRS to 1.25 and lost five people. Nothing stopped it, and by current policy nothing should: exploration is deliberately unconstrained and only the *final answer* must keep everyone alive. Whether a soft floor should apply once a chain has a known-survivable design is a genuine open question, not an oversight — recorded here so the choice stays a choice.

## P2 — Prune the designer-facing context further

Volume is not in the score, and `over_budget` duplicates what cost and mass already say. Both stay in the logs; both should drop out of the decision page. Partially done in phase 3; finish it in `design_state.py`.

## P2 — Candidate id and applied round, side by side

A chain's best round and its final round can differ (phase 3: 84.23 at round 41, 84.08 at round 50). Small, but it makes chain output ambiguous. Print both the selected candidate id and the round it was applied in (`chain_selection.py`, `output.py`).

---

## Beyond the current loop

Further out, and honestly speculative — listed with what would have to be true first.

**More than one designer.** Today the design side is deliberately a single engineer (`agents.yaml`: *"the question is whether ONE agent can gather its own evidence and reach a design"*). A review board — proposer, sceptic, cost owner — is the obvious next question, and the roster machinery for it already exists (the classic non-tool-use designer still deliberates with four). It needs the single-agent baseline settled first, or a multi-agent result cannot be attributed.

**An LLM crew under an LLM designer.** Supported today and rarely run, because a non-deterministic crew means a design's measured effect is confounded with a different crew improvising differently. `candidate_actor_mode` exists to score candidates with the cheap crew while the baseline keeps the expensive one; what is missing is the experiment design, not the code.

**Subsystems beyond ECLSS.** The EPS (power) ROS 2 bridge already exists (`environment/ssos/eps/`). ECLSS sized against a power budget is a materially harder and more realistic design problem: the two subsystems compete for the same mass and the same watts.

**Design variables that are not capacities.** Redundancy count, machine placement, operating policy. Each needs a sizing model before it can be scored, which is the actual work — `rack_affine_linear_v1` is one paragraph of arithmetic and the honest reason the variable set is three.

**Beyond a space habitat.** The loop — precise world rules, raw-data-only agent inputs, a deterministic scorecard, a design proposal fed back as next round's constraints — is not specific to ECLSS. Any bounded resource system with a real cost function fits it: a datacentre under a power cap, a factory line, a supply chain. What transfers is the machinery; what does not transfer for free is the physics model, and without one the whole thing is a chat log.

---

## See also

- [Experiment record](results.md) — the measurements these priorities come from
- [Implementation specs](specs/index.md) — how a change gets specified before it gets built
- [Development plan](development-plan.md) · [Backlog](memo/backlog.md)
