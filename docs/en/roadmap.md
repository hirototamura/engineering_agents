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
| Assert a partial proposal does not reset the omitted fields to baseline | `design_proposals.py` | currently **fails by design** — see P1 |
| Keep an observed failure boundary as a bad pattern | `chain_memory.py` `known_bad_patterns` | WRS=1.25 → 45/50 survives into the next round's note |

## P1 — Make chain memory *apply*, not only *show*

The largest known gap, and the code says so in its own docstring: chain memory tells the next round what worked, but a partial proposal still drops the fields it omits. Showing the note was enough in practice — one reset in fifty rounds instead of twelve — but the mechanism is a warning label, not a fix.

**The fix:** merge `applied_proposals` into a cumulative design state, so an unnamed field keeps its installed value rather than falling back to the scenario default. That is a change to how proposals are carried (`design_proposals.py`), not to what the designer is told.

**Why it was not done first:** it changes the meaning of every proposal in the archive, and the cheaper intervention was worth measuring on its own. It was. Now the expensive one is worth doing.

## P1 — Explore more than one axis

Phase 3's stagnation detector fires and asks for exploration, and the exploration it gets is still WRS-only. ARS and OGS have not moved since they reached their theoretical floor.

| Direction | Rationale |
| --- | --- |
| Hold ARS ≥ 20.8, OGS ≥ 42.0 as a floor | below it the crew dies; this is physics, not preference |
| Concentrate on WRS 1.8–2.2 | the observed promising band |
| Avoid WRS ≈ 1.25 | measured failure boundary (45/50) |
| When WRS alone stops paying, perturb ARS/OGS by 1–3 % | the one axis pair never tried |
| Deprioritise *lowering* ARS/OGS | high prior probability of losing the crew |

Lands in `chain_memory.py` `_exploration_directive`, which already composes the text the next round reads.

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
