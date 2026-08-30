# Experiment record — three fifty-round chains

Three fifty-round design→verify chains were run against the same world, the same crew of fifty, and the same non-survivable baseline. Between them, two things changed: first the chain was given a memory, then the scorecard's cost and mass axes were re-anchored. Nothing else — same simulator, same actors, same tools.

This page is the measured result. Every number below is read from the per-round metrics committed under [`docs/data/`](https://github.com/hirototamura/engineering_agents/tree/main/docs/data) — 50 rows × 54 columns per phase, one row per round, plus the figures generated from them.

| | Phase 1 — as built | Phase 2 — + chain memory | Phase 3 — + re-anchored scorecard |
| --- | ---: | ---: | ---: |
| Rounds | 50 | 50 | 50 |
| Baseline replay survivors | 0/50 | 0/50 | 0/50 |
| **Final replay survivors** | **34/50** | **50/50** | **50/50** |
| Rounds at 50/50 | 34 | 49 | 48 |
| Rounds at 0/50 | 12 | 1 | 1 |
| Complete design proposals | 38/50 | 50/50 | 50/50 |
| Catastrophic ARS/OGS reset | 12 | first round only | first round only |
| Unique designs explored | 39 | 11 | 17 |
| Best score | 66.18 | 66.36 | 84.23 |
| Mean score | 61.71 | 65.94 | 83.34 |
| Final score | 55.41 | 66.36 | 84.08 |

!!! warning "Phase 3 scores are not comparable to phases 1–2"
    Phase 3 changed the scoring function. Its 84-point results are largely the cost/mass axes paying out differently, **not** a design that got 18 points better. The behavioural facts that *are* comparable across all three: survivors, reset count, proposal completeness, unique designs.

![Survivors and score across all three phases](../images/results/ssos_phase1_phase2_phase3_survival_score_trend.svg)

---

## Phase 1 — the loop worked and the chain still lost the crew

The mechanism was sound. Each round gathered its own evidence, simulated its candidate, audited the physics, ranked, and handed a design on. Round 24 found `ARS=20.8, OGS=42.0, WRS=1.8` and kept all fifty people alive at 66.18 points.

Round 25 proposed a WRS-centred change. The next run came back **0/50**.

```
round 24: ARS=20.8  OGS=42.0  WRS=1.8    → 50/50 alive, 66.18
round 25: a partial proposal, WRS only
          → next run installs ARS=4.5, OGS=9.25 (baseline)  → 0/50
```

The design that worked was not rejected. It was forgotten. Each round reads *its own run and nothing else* — which is exactly what makes a round auditable, and exactly why the chain had no memory. This happened twelve times in fifty rounds, and 12 of 50 proposals arrived incomplete.

The final round ended at 34/50 and 55.41 — **worse than round 24**, twenty-six rounds after the answer had already been found.

The diagnosis is worth stating precisely, because it is not the obvious one: **this was not a search failure. It was a state-inheritance failure.** Phase 1 explored 39 unique designs — more than either later phase — and reached good ones repeatedly. It just could not hold onto them.

---

## Phase 2 — one 4 KB note

The only change: `compact_chain_memory.json`, capped at 4096 bytes, carrying the best full-survival design, the sizing actually installed last round, a *calculated* floor under each subsystem, and up to five ways this chain has already lost the crew. It is *shown* to the next round; nothing applies it. (Both of those changed in `0aaec84`, after these runs — the floor is measured now and the hand-off is completed. What follows is what these three chains actually ran with.)

| | Phase 1 | Phase 2 |
| --- | ---: | ---: |
| Final replay survivors | 34/50 | **50/50** |
| Rounds at 0/50 | 12 | **1** (the first) |
| Proposals naming all three subsystems | 38/50 | **50/50** |

Every round from 2 onward held 50/50. Every proposal named all three subsystems.

The cost is visible in the same table. Unique designs fell from 39 to 11: the chain pinned ARS and OGS at their theoretical floor and searched WRS alone, oscillating around 1.5625 / 1.875 / 2.1875. Best score moved 0.26 points across the whole chain.

Memory stopped the collapse and narrowed the search. Both are real.

---

## Phase 3 — the scorecard was measuring the wrong thing

Phase 2's inspectable score breakdown showed the actual problem. A design that kept fifty people alive was scoring **11.57 out of 40** on cost and mass.

The reason was the anchor. Full marks sat at the *shipped baseline* — 1800 kg, 259 M$ — which loses all fifty occupants. Every survivable design is necessarily larger than a design that keeps nobody alive, so every survivable design was marked as expensive, and two very different survivable designs came out at 11.6 and 4.1 out of 40. The sheet could no longer tell them apart.

Phase 3 moved the full-marks line to near the smallest design observed to keep everyone alive (~605 M$ / 4091 kg), with zero at 900 M$ / 6000 kg:

```yaml
evaluation:
  footprint:
    cost_full_score_musd: 500.0
    cost_zero_score_musd: 900.0
    mass_full_score_kg: 3400.0
    mass_zero_score_kg: 6000.0
```

Cost and mass on a surviving design went from 5–6 points each to 14. Unique designs rose from 11 to 17.

Score composition, phase 1 (survivable designs squeezed into a narrow cost/mass band) against phase 3 (the same designs, re-anchored):

![Phase 1 score composition](../images/results/phase1_score_components_grouped.svg)

![Phase 3 score composition](../images/results/phase3_score_components_grouped.svg)

Those four blocks roll cost and mass together, and cost and mass are the whole argument here, so the same score split into all seven axes — A survival, B time-to-clear, C environment, D recovery, **E cost, F mass**, G ops/physics:

![Phase 1, all seven axes](../images/results/phase1_score_components_stacked_split.svg)

![Phase 3, all seven axes](../images/results/phase3_score_components_stacked_split.svg)

E and F move together and by almost the same amount, which is the point: nothing about the design made it disproportionately cheaper *or* lighter. The anchor moved, and both axes started paying out. Per-round values for all three phases are in `docs/data/phaseN_score_components_split.csv`.

Best round (41) against final round (50):

| Axis | Round 41 | Round 50 |
| --- | ---: | ---: |
| A Survival | 20.00 | 20.00 |
| B Time-to-clear | 10.00 | 10.00 |
| C Environment | 9.98 | 9.98 |
| D Recovery | 6.14 | 6.06 |
| E Cost | 14.71 | 14.76 |
| F Mass | 14.66 | 14.71 |
| G Ops / physics | 8.75 | 8.57 |
| **Total** | **84.23** | **84.08** |

Round 34 dropped WRS to 1.25 and lost five people (45/50) — the only non-50/50 round after the first. That is a useful boundary, and the kind of fact chain memory is meant to keep.

---

## What the design variables actually did

![ARS / OGS / WRS across all three phases](../images/results/ssos_phase1_phase2_phase3_parameter_trends.svg)

In phases 2 and 3, ARS settles at 20.8 kg/day and OGS at 42.0 kg/day and stays there. Those are not arbitrary: they are exactly the nameplates `compute_theoretical_capacity` reports as required for this crew (`theory_ars_required_nameplate=20.8`, `theory_ogs_required_nameplate=42.0` in every row of the metrics CSVs; OGS 42.0 is 50 × 0.84 kg O₂/day). The chain found the physical floor and refused to go under it.

That refusal has since been re-examined, and the re-examination is the most interesting thing these three runs produced. The floor was *calculated* and *asserted* — and a line a designer may not cross becomes the answer. From the round the two gas subsystems first touched theirs, twenty further rounds moved neither; they are 91% of the mass, which is why the search collapsed onto the water recycler. One of the three figures was also simply wrong: the calculated water minimum of 1.5625 L is really about 1.98, because the crew only starts the recycler once five litres have collected, and three rounds lost four occupants each rediscovering that. `floor_probe.py` (`0aaec84`) measures the bracket instead of asserting it, and shows the designer both ends and no threshold. A fourth chain has not yet been run with it.

Search then concentrated on WRS. The most frequent designs in phase 3:

| ARS | OGS | WRS | Rounds |
| ---: | ---: | ---: | ---: |
| 20.8 | 42.0 | 1.5625 | 9 |
| 20.8 | 42.0 | 2.0 | 7 |
| 20.8 | 42.0 | 1.75 | 6 |
| 20.8 | 42.0 | 1.8 | 5 |
| 20.8 | 42.0 | 1.6 | 5 |

Promising range: WRS 1.8–2.2. Failure boundary: WRS ≈ 1.25.

---

## What is honestly still wrong

Stated plainly, because a result page that only lists wins is not a result page.

1. **Total mass and cost did not improve much between phase 2 and phase 3.** The score went up because the scoring changed. The correct reading is "survivable designs stopped being marked unfairly", not "the design got lighter". Future reports should print the new score, the old score recomputed, total M$, total kg, and survivors side by side, so the two can never be confused again.
2. **The search is still WRS-only.** ARS and OGS have not been perturbed since they hit the floor. The stagnation detector now fires and asks for exploration, but the exploration it gets is still along one axis.
3. **~~Chain memory shows; it does not apply.~~ Fixed in `0aaec84`, after these runs.** A capacity proposal was merged into the *scenario file* rather than into the machine the run was flying, so naming one subsystem silently returned the other two to their shipped sizes — that is the mechanism behind every reset counted above. `complete_capacity_profile` now fills in whatever a proposal did not mention from what was actually installed. The note stops being a stopgap; the numbers on this page pre-date the fix.
4. **No safety floor during exploration.** Round 34's WRS=1.25 cost five lives. Nothing stopped it, and nothing had to: exploration is deliberately unconstrained, and only the *final answer* must keep everyone alive. Whether that is the right trade is an open question, not a settled one.
5. **The measured floor is unmeasured, as a result.** `0aaec84` also removed the asserted minimum, which is what pinned ARS and OGS through most of phases 2 and 3. Whether the search actually spreads once nothing forbids going lower is the obvious next run, and it has not been done.
6. **One model, one seed, three chains.** These are three runs, not a statistical study. They are enough to show a mechanism working and a mechanism failing; they are not enough to put an error bar on a score.

---

## Where the numbers come from

| Artifact | Contents |
| --- | --- |
| `<chain>/NN/summary.json` | one round's outcome |
| `<chain>/NN/evaluation.json` | that round's scorecard, per axis, with `points_lost` |
| `<chain>/NN/design_decision_state.json` | the page the model was shown, and what it answered |
| `<chain>/NN/design_proposals.json` | the sizing that was handed on |
| `<chain>/compact_chain_memory.json` | the note the next round read |
| `<chain>/chain_summary.json` | the chain's single answer and how it was selected |

All three chains are archived whole — [`experiments/runs/`](https://github.com/hirototamura/engineering_agents/tree/main/experiments/runs), 11 MB compressed each — together
with the scripts that turn them into the tables on this page. Re-running the analysis reproduces
every figure and every CSV byte for byte, and the last step of the instructions is a `diff` that
proves it: [`experiments/README.md`](https://github.com/hirototamura/engineering_agents/blob/main/experiments/README.md).

Run a new chain with:

```bash
./scripts/run_design_chain.sh --rounds 50
```

The simulator is deterministic, so a chain re-run with the same LLM replies reproduces exactly. The LLM replies themselves are not — temperature is 0.45 — which is why the per-round design_decision_state is written whole.

---

## See also

- [Implementation specs](specs/index.md) — the spec each of these three changes was written against
- [Agent design](agent-design.md) — what the model was shown at each of these points
- [Design agent](memo/ssos_eclss_loop/tool_use_design_agent.md) — the loop in detail
