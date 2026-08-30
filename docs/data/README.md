# Measured data — three fifty-round chains

Per-round metrics behind [the experiment record](../en/results.md) / [実験記録](../ja/results.md). Extracted from the run artifacts of three `ea run ssos_eclss_loop --iterate 50` chains against the same world, the same fifty-person crew, and the same non-survivable baseline.

| Phase | What changed | Files |
| --- | --- | --- |
| 1 — as built | nothing; the loop as it first shipped | `phase1_*` |
| 2 — chain memory | `compact_chain_memory.json` carried between rounds | `phase2_*` |
| 3 — re-anchored scorecard | `evaluation.footprint` full-marks line moved off the non-surviving baseline | `phase3_*` |

**Phase 3 scores are not comparable to phases 1–2** — the scoring function itself changed. Comparable across all three: `crew_remaining`, `config_ars` / `config_ogs` / `config_wrs`, `proposal_*`, `physics_gate_passed`, `constraint_status`.

## Files

| File | Contents |
| --- | --- |
| `phaseN_iteration_metrics.csv` | one row per round, 54 columns |
| `phaseN_iteration_findings.json` | derived findings for that chain (resets, best round, stagnation) |
| `phaseN_score_components_grouped.csv` | the scorecard rolled up into four blocks per round: survival, system behaviour (B–D), footprint (cost + mass), ops/physics. The seven individual axes are the `axis_*` columns of the metrics CSV |

## Columns worth knowing

| Column | Meaning |
| --- | --- |
| `crew_remaining` / `crew_lost` | out of 50. The only axis with a hard clearance line |
| `config_ars` / `config_ogs` / `config_wrs` | the sizing this round actually ran with |
| `proposal_ars` / `proposal_ogs` / `proposal_wrs` | the sizing this round handed on. Blank ⇒ a partial proposal, the phase-1 failure mode |
| `theory_*_required_nameplate` | what `compute_theoretical_capacity` says this crew needs. Constant across rounds — it is a property of the crew, not the design |
| `theory_*_coverage` | installed ÷ required |
| `score` and `axis_*` | the scorecard total and its seven axes |
| `expected_*` vs actual | what the candidate re-simulation predicted vs what the next round measured. These agreeing to the decimal is how the recursive loop is verified as closed |
| `physics_gate_passed` | the nine telemetry-only mass-balance checks |
| `constraint_status` | `ok` / `over_budget` / `out_of_bounds` |
| `final_status` | `approved` / `provisional_final` / `rejected_final` |
| `tool_counts` | which of the nine tools were called, and how often |
| `llm_turn_count` / `tool_call_count` | how much of the round was model vs. deterministic code |
| `total_mass_kg` / `total_cost_musd` / `total_volume_m3` | what the design would cost to build and launch |

## Reproducing

```bash
ea run ssos_eclss_loop --iterate 50
```

The simulator is deterministic. The LLM is not (temperature 0.45), so a re-run explores a different path — which is why each round's `design_decision_state.json` is written whole rather than summarised.
