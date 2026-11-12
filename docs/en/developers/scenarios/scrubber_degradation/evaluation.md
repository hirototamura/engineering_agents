# Scrubber evaluation

This scenario reports deterministic health and recovery metrics from a mock ECLSS/EPS station. It does not use the SSOS scorecard, cube screening, or a project-wide numerical score. For reading existing outputs, use the [user results guide](../../../users/scenarios/scrubber_degradation/results.md).

## Authoritative checks

[environment/scrubber/eclss_ops/telemetry.py](https://github.com/hirototamura/engineering_agents/blob/main/src/environment/scrubber/eclss_ops/telemetry.py) owns `co2_health()`, `power_health()`, `overall_health()`, and their shared constants. The authoritative public values and inclusivity rules are in the [results guide](../../../users/scenarios/scrubber_degradation/results.md#bands-and-recovery-indicators).

Keep the operational/recovery constant distinct from the health-band constants. Labeled control, recovery timing, and the dashboard reference line share that operational threshold, while overall health chooses the worse resource status. These are model-specific checks; changes must preserve the intended equality behavior and update the owning user contract.

## Summary semantics

`scenario_run.py` records peak CO₂, minimum power margin, final telemetry/health, anomaly presence, first CO₂ crossing of the recovery threshold, the later first return below it, first applied EPS boost, and recovery from critical power. No observed transition means a nullable timing field, not zero recovery time.

The run logs pre-operation rows and same-step post-operation actuator/EPS updates. Some peak/timing accumulation happens before team actions; final fields can reflect the later refreshed observation. Preserve that distinction when changing aggregation. An EPS request event proves admission/scheduling, not an instantaneous physics improvement.

## Test the observations behind each summary

| Computation | Source and timing | Regression to preserve |
| --- | --- | --- |
| Health classification | `telemetry.py` on the observed snapshot | Equality behavior and worse-resource aggregation |
| Peak/minimum | Runner accumulation on step observations | Do not count post-operation refresh as another interval |
| CO₂ recovery | First crossing and first later return | No crossing/recovery remains null |
| Power recovery | First exit after a critical observation | Initially safe is not a recovery |
| EPS boost timing | Applied recovery event, filtered by command kind | A rejected request is not applied support |
| Final state | Last snapshot, including same-step refresh | Summary and recorded actuator/EPS state agree |
| Design proposal | Post-run team output | Preview is not measured after-state |

The original documentation's before/after graph is useful for explaining proposed topology. A test of `apply_dict_change()` proves preview transformation only; the closed-loop test must eventually assert a distinct second run's consumed design and measured response.

## Regression and scope

Use `tests/scenario/test_scrubber_baseline.py`, `test_scrubber_with_agents.py`, and environment mock/station tests. Cover equality at each threshold, no anomaly, no recovery, rejected boost, support expiration, and consistency between final summary and recorded rows. Changing shared constants also affects labeled policy and viewer reference values; update all readers deliberately.

The evidence establishes behavior of the mock model and orchestration. It does not establish physical life-support performance. A post-run proposal has no measured after-state until a separate simulator run applies it; the current scrubber implementation does not perform that reinjection.
