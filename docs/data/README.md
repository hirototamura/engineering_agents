# Measured data — four fifty-round chains

Per-round metrics behind [the experiment record](../en/results.md) / [実験記録](../ja/results.md). Extracted from the run artifacts of four `ea run ssos_eclss_loop --iterate 50` chains against the same world, the same fifty-person crew, and the same non-survivable baseline.

| Phase | What changed | Files |
| --- | --- | --- |
| 1 — as built | nothing; the loop as it first shipped | `phase1_*` |
| 2 — chain memory | `compact_chain_memory.json` carried between rounds | `phase2_*` |
| 3 — re-anchored scorecard | `evaluation.footprint` full-marks line moved off the non-surviving baseline | `phase3_*` |
| 4 — audit panel | one unlensed designer, three independent auditors, item-veto merge | `phase4_*` |

**Phase 3 and 4 scores are not comparable to phases 1–2** — the scoring function itself changed before phase 3. Phase 4 uses the same scorecard as phase 3. Comparable across all four: `crew_remaining`, `config_ars` / `config_ogs` / `config_wrs`, `proposal_*`, `physics_gate_passed`, `constraint_status`.

## Files

| File | Contents |
| --- | --- |
| `phaseN_iteration_metrics.csv` | one row per round, 54 columns |
| `phaseN_iteration_findings.json` | derived findings for that chain (resets, best round, stagnation) |
| `phaseN_score_components_grouped.csv` | the scorecard rolled up into four blocks per round: survival, system behaviour (B–D), footprint (cost + mass), ops/physics |
| `phaseN_chain_key_summary.csv` | the chain's own headline figures: rounds requested and completed, survivors first / last / baseline replay / final replay, verdict |
| `ssos_three_way_comparison_summary.json` | the four phases side by side — the source of the comparison table in the experiment record |
| `phaseN_score_components_split.csv` | the same score with all seven axes separate — A survival, B TCL, C environment, D recovery, **E cost, F mass**, G ops/physics. Use this one when the question is cost *against* mass; the grouped file adds them together |

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

## Where this came from

These files are not hand-maintained. They are the output of
[`experiments/analysis/analyze_ssos_iter.py`](../../experiments/analysis/analyze_ssos_iter.py)
run over the raw chain logs archived in
[`experiments/runs/`](../../experiments/runs), and re-running it reproduces them
byte for byte:

```bash
cd experiments
for f in runs/*.tar.gz; do tar -xzf "$f" -C runs/; done
python3 analysis/analyze_ssos_iter.py --root runs/phase1-no-chain-memory --prefix phase1
diff outputs/phase1_iteration_metrics.csv ../docs/data/phase1_iteration_metrics.csv   # empty
```

Full instructions, and what is inside a chain archive:
[`experiments/README.md`](../../experiments/README.md).

## Running a new chain

```bash
./scripts/run_design_chain.sh --rounds 50
```

The simulator is deterministic. The LLM is not (temperature 0.45), so a re-run explores a different path — which is why each round's `design_decision_state.json` is written whole rather than summarised.
