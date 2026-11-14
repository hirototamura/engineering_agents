# Interpret cube evidence

Start with `summary.json`: execution status, selected candidate, stop reasons, screening/validation results, GPU status, and publication state are separate fields. A successful process does not promote a physical design.

## Screening, selection, and validation

The reference is simulated before proposal generation. Every candidate uses the complete frozen exploration matrix. The exploration-selected best design then uses a separate frozen validation matrix. Criteria and required duration come from the SSOT contract.

The exploration objective is:

```text
screening_pass_fraction
− rms_penalty × mean(final_1s_tilt_rms_deg)
− torque_proxy_penalty × mean(continuous_torque_exceeded_fraction)
```

Penalty coefficients come from `plan.objective`. The torque term is a proxy; it is not electrical energy or thermal prediction. Read case outcomes and constraints as well as the aggregate objective.

CPU results are the screening source even when GPU is requested. GPU verification checks full-episode gate outcomes and a trajectory prefix under fixed time step, declared tolerances, duration/status agreement, and near-gate exclusion. It does not perform half-step adjudication.

CPU-only success can be `status: completed` while the selection remains `provisional`. `numerically_confirmed` requires completed independent validation, all screening passed, and passed GPU agreement. Missing GPU is `not_run`, not substitute CPU evidence. `physical_verified` remains false; `physical_fidelity`, electrical energy, and temperature predictions remain null. Numerical agreement does not establish model fidelity or hardware compliance.

## Retained records

`frozen-snapshot.json`, `environment.json`, and `policy-initial.json` identify inputs. `candidates/candidate-NNN/compiled.json` and `result.json` retain each evaluated design. Completed phases under `round-NN/` retain SSOT context, prompt/proposal, and policy records; failed/rejected/pending records preserve unfinished work. `validation/` holds the independent compiled design and results.

`design_proposals.json` contains selection evidence and the proposed handoff. `onepiece-outbox.json`, `sync-status.json`, and `publication/summary.json` distinguish local evidence from delivery to One Piece. A pending publication can stop further proposal work while preserving local records and the durable outbox. Optional `memory/episodes.jsonl` is advisory design context, not verification authority.

## Isaac evidence limits

`conversion.json` and `usd-audit.json` describe conversion and authored USD values, not contact-solver equivalence. A pilot is wiring evidence with ideal sensing; it does not implement the full delay/noise model. Campaign analysis refuses incomplete/altered trial plans, provenance mismatches, duplicate trials, and missing cases.

Wilson intervals describe success in the seeded initial-condition distribution. Paired comparisons are descriptive and report unadjusted p-values; selection claims need fresh validation seeds. These reports do not establish cross-backend agreement, model fidelity, or hardware uncertainty. An `isaac propose` output is a new hypothesis requiring a new measured campaign.

## Read metrics before the aggregate

| Quantity | How it is formed | Interpretation limit |
| --- | --- | --- |
| `final_1s_tilt_rms_deg` | Square root of mean squared total tilt over the episode's final one-second window | Early failures also have a last window; the independent duration gate still matters |
| `contact_fraction` | Fraction of post-initial sampled observations with normal force above the model cutoff | A sampled model contact indicator, not hardware reliability |
| `continuous_torque_exceeded_fraction` | Fraction of integrated physics steps where any wheel exceeds the comparison threshold | Not averaged over three wheels; not a temperature prediction |
| `speed_governor_fraction` | Fraction of physics steps where the governor blocks further same-direction acceleration | Different from peak speed alone |
| `screening_pass_fraction` | Cases satisfying every frozen gate / all declared cases | Depends on the selected trial distribution |

The RMS definition from the original walkthrough is:

```text
e_RMS = sqrt((1/N) × Σ(theta_i²))
```

`theta_i` is total tilt, not a separate mean of two axis errors. Sampled telemetry and physics-step counters have different denominators. Use the saved time grid and counter definitions when reproducing a report calculation.

### Worked historical score — October 2026

The 20 October code/evidence walkthrough records this **GPU-parallel projection** of the October 17 upper-wheel study:

```text
J = k/12 − 0.05 × mean(e_RMS) − 0.2 × mean(f_tau)
J = 12/12 − 0.05(0.1699230270) − 0.2(0) = 0.9915038486
```

These are the original formula and recorded numbers, not a new evaluation. The coefficient values and twelve-case denominator belong to that frozen study; a new run must read its own `plan.objective` and matrix.

| Historical record | Implementation / conditions | Recorded score |
| --- | --- | ---: |
| Upper-wheel retained study design | Native MuJoCo; runtime selection source | 0.9916124707 |
| Same study design, later report projection | Saved MJX summaries; 12 passing cases | 0.9915038486 |
| Fresh GPU audit | Separate audit conditions | 0.9914858776 |
| Lower-wheel first trial | Native exploration, 12 passing cases | 0.9885861309 |

Do not join those rows into one progress curve. They differ in implementation or conditions, and the full lower-wheel twelve-case GPU score was unmeasured in the original audit. A score near 0.99 is not a 99% hardware success probability. The original scalarization gives one extra passing case `1/12 = 0.083333`, a 0.1° reduction in mean RMS `0.005`, and a one-percentage-point reduction in torque exceedance `0.002`; those are numerical policy weights, not physical law.

The original first-trial report also records that a specific known failure improved while the aggregate score worsened. That is a useful reason to read both the case table and the objective. Sources: [20 October walkthrough](https://github.com/hirototamura/engineering_agents/blob/648237d8596462362b5772914242a3881f82ad35/docs/en/balancing_cube_simulation_walkthrough.md), [first lower-face trial](https://github.com/hirototamura/engineering_agents/blob/648237d8596462362b5772914242a3881f82ad35/docs/en/bottom_corner_trial.md), and [workflow study](https://github.com/hirototamura/engineering_agents/blob/648237d8596462362b5772914242a3881f82ad35/docs/en/balancing_cube_workflow_study.md). These English source reports retain the original experiment scope; they do not adopt a hardware baseline.

## Read Isaac distributions with their denominator { #isaac-distributions }

The original 24 October campaign analysis retained median trajectories and central **68.3%, 95.5%, 99.7%, and 100% empirical coverage** at each time. These are pointwise state distributions, not confidence intervals around a mean or an assumption of Gaussian errors. Different mechanical configurations must be plotted separately.

| Analysis mode | Included samples after a recorded evaluation stop | What a late-time band means |
| --- | --- | --- |
| `all-recorded` | All recorded motion remains, including free evolution after controller stop | The selected cases' recorded outcomes, including fallen cubes |
| `evaluation-only` | Each case contributes through its stop sample, inclusively | A distribution conditional on still being evaluated; sample count can shrink |

The historical reference corner 001 at 3 s illustrates the difference: the upper 97.75 percentile was approximately **57.245°** for all recorded cases and **0.176°** for evaluation-only cases. Those are not two improvements of the controller; the denominator changed.

Always retain per-time `count`, `evaluation_count`, selected identities, outcome filters, and the post-stop policy. The analysis does not fill missing post-stop samples. Recorded tilt is geometric truth, not the controller's noisy feedback. In the historical pack, post-stop motor channels could contain a hypothetical computed request while actual sent effort was zero; tilt alone cannot reconstruct full case videos.

The [original campaign-analysis guide](https://github.com/hirototamura/engineering_agents/blob/648237d8596462362b5772914242a3881f82ad35/docs/en/isaac-campaign-analysis.md) identifies the two 24,576-case campaigns and their evidence limits. Use the [existing-data workflow](running.md) to inspect compatible saved campaigns; this analysis does not run physics, tune gains, or change gates.
