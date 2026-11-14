# Change evaluation

Start by naming the changed claim: constraint admissibility, optimization, model invariants, numerical agreement, or physical validation. Read the [evaluation responsibilities](../evaluation.md) and selected [scenario evaluator](../scenarios/index.md) before editing a formula.

## Trace and implement the change

1. Identify the authoritative requirement and the exact persisted inputs. Define units, time-row selection, horizon, missing/non-finite behavior, and applicability.
2. Locate every consumer: run summary, candidate ranking, final-answer selection, chain memory, dashboard, and report. Keep one authoritative computation rather than adding a competing score in a viewer.
3. Change the scenario-owned evaluator. SSOS finalization must remain before post-run design and write the run measurement once. Cube screening and numerical agreement must remain separate from its optimization objective.
4. If semantics or score weights change, update the schema/version and comparability statement where applicable. Record a new requirement or contract revision when authority changes. Never silently reinterpret a historical score under a new formula.
5. Update the user explanation of the result and developer explanation of the contract in both languages. Retain the distinction between a proposal and a simulated candidate.

## Change-impact matrix

| Changed behavior | Check the owning computation | Check downstream use |
| --- | --- | --- |
| Time aggregation | Pre/post row selection and actual time interval | Trajectory summaries and displayed final state |
| Hard constraint | Missing/non-finite and exact equality behavior | Candidate eligibility and adoption distinction |
| Objective or weight | Version and comparable input set | Ranking, incumbent, memory, report projection |
| Physics audit | Required telemetry terms and residual tolerance | Incomplete versus failed versus unexecuted |
| Numerical agreement | Paired keys, interval and tolerances | GPU-not-run cannot become verified |
| Applicability | Raw evaluator and finalizer together | Persisted status and nullable/boolean summary indices |

Applicability deserves its own regression because a finalizer can invalidate a raw non-applicable result. The SSOS [evaluation contract](../scenarios/ssos_eclss_loop/evaluation.md) records that current limitation; testing the pure evaluator alone would miss it.

## Required evidence

Test values just below, at, and above each gate; missing values, booleans in numeric fields, non-finite numbers, incomplete trajectories, duplicated trials, and unsupported contracts where relevant. Test ranking with invalid candidates and ties. A high optimization score must not bypass hard constraints or absent evidence.

SSOS regression areas include canonical pre/post-operation rows, physics-gate incomplete states, integrity invalidation, candidate eligibility, chain final answers, and score maxima with/without actors. Cube areas include frozen trial matrices, complete duration, fixed-dt CPU/GPU comparison, near-gate inconclusive behavior, unavailable GPU, partial rollout retention, and synchronization failure.

Run focused tests, then the [ordinary verification commands](../contributing.md). Do not run historical experiment rescoring as a side effect of changing documentation. If a separate research comparison is authorized, retain both evaluator versions, inputs, and conditions so its result can be audited.
