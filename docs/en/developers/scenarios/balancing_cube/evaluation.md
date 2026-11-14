# Cube evaluation

[evaluation.py](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/balancing_cube/evaluation.py) separates screening, objective aggregation, and CPU/GPU agreement. The authoritative criteria and trial plan come from the frozen SSOT snapshot. Public result fields are explained in the [user results guide](../../../users/scenarios/balancing_cube/results.md).

## Complete numerical evidence

`screening()` applies supported comparison operators to contract metrics and requires completed simulation for the declared duration. Numeric inequalities reject booleans and non-finite values. `aggregate()` requires exactly the expected unique `(domain_id, condition_id, seed)` matrix and rejects empty/non-finite evidence. The score combines screening pass fraction with the frozen RMS and torque-proxy penalties; a better objective is not permission to alter gates or trial conditions.

The aggregate's CPU verification flag identifies completed numerical evidence under this contract, not universal engineering acceptance or physical validation. GPU verification additionally requires every paired comparison to pass.

## Fixed-dt CPU/GPU agreement

`paired_metrics()` checks sufficient trajectories, finite increasing timestamps, complete comparison coverage, required finite series, and gaps. It computes prefix trajectory RMSE and wheel-peak difference under contract tolerances, then also compares termination state/time and full-episode screening decisions.

A metric near a screening gate makes agreement inconclusive. The current comparison reports `half_step_adjudication_performed: false`; it does not run a half-step adjudication or reuse historical half-step evidence as a new result. Missing or failed GPU execution cannot be reported as GPU verification. Agreement of two numerical implementations does not establish model fidelity to hardware.

## Objective and numerical-source separation

The aggregate computes the frozen objective from native CPU summaries:

```text
J = N_screening_pass / N_trials
    − objective.rms_penalty × mean(final_1s_tilt_rms_deg)
    − objective.torque_proxy_penalty × mean(continuous_torque_exceeded_fraction)
```

This is an engineering scalarization, not a probability of physical success. The coefficients are taken from the snapshot, not supplied by the model. A report may recompute the same expression from saved GPU summaries, but that projection is not the runtime selection input: `adapter.py` explicitly labels each trial `evaluation_summary_source: native_cpu_reference` and stores `gpu_summary` separately. Do not mix those curves without identifying the source.

| Evidence state | Recorded meaning | Not established |
| --- | --- | --- |
| Native trial matrix complete | CPU-based screening and objective available | GPU agreement or hardware fidelity |
| GPU `not_run` | No accelerated evidence, with reason | CPU fallback is not GPU execution |
| GPU `completed` | Accelerated summaries/trajectories available | Agreement until paired checks pass |
| Paired `verified` | Full-episode gates and prefix tolerances passed | Physical validation or half-step adjudication |
| Paired `inconclusive` | Missing/invalid interval, near gate, or disagreement | Permission to call agreement verified |
| Validation `completed` | Independent matrix executed for one selected candidate | Automatic acceptance if its checks fail |
| `selection_status: numerically_confirmed` | Completed validation, all screening passed, GPU agreement true | Hardware baseline adoption |

CPU-only work can complete a numerical development run while selection remains provisional. Conversely, requesting GPU and not executing it makes the required evidence incomplete. The loop distinguishes these states rather than treating all non-errors as one engineering pass.

## Agreement calculations and data scope

For paired series, the code interpolates GPU values at CPU times in the allowed prefix and computes:

```text
RMSE(x) = sqrt(mean((x_CPU(t_i) − interpolate(x_GPU, t_i))²))
```

It uses tilt RMSE, the largest axis angular-rate RMSE, pivot-displacement RMSE, and wheel-peak difference. Timestamp coverage/gaps, termination agreement, and equality of full-episode screening decisions are additional conditions. The prefix comparison and full-episode gates answer different questions and both remain recorded. See [paired_metrics()](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/balancing_cube/evaluation.py).

## Failure and test scope

The adapter retains deadline/execution failures as partial evidence without an aggregate score. The loop preserves reference failures, incomplete required factorial comparisons, frozen-context changes, and sync failures as stopped/inconclusive outcomes. Do not select a partially evaluated candidate because its completed subset looks better.

The current aggregate explicitly leaves physical fidelity, electrical energy, and temperature prediction unestablished; physical verification is false. Any expansion needs a separately defined model/evidence contract.

Use `tests/scenario/test_balancing_cube.py` for finite data, complete trial matrices, agreement scope, near-gate behavior, unavailable GPU, incomplete evidence, factorial rollback, and final delivery failures. Keep optional simulator tests distinct from controlled orchestration tests, and state which environment actually ran when reporting validation.
