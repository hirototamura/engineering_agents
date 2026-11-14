# Change a simulator backend

A backend change must preserve the scenario's observation and operation meanings, not merely satisfy a Python method signature. Start from the selected [scenario implementation](../scenarios/index.md) and identify units, clock behavior, failure flags, and evidence requirements.

## Choose the owning contract

Scrubber's `SimulatorProtocol` is step-driven and returns scrubber telemetry. SSOS's `EclssBackend` polls storage telemetry and exposes ARS/OGS/WRS actions, storage services, and subsystem failures; mock and plant backends additionally support explicit advancement. Cube's `BalancingCubeAdapter` coordinates compile/rollout/feedback, while `environment/mujoco` owns numerical execution. Do not make one of these domain contracts universal just to add a backend.

Implement model and transport behavior under `environment`. Wire construction and scenario-specific configuration under the owning runner. Update CLI admission only for supported scenario/backend combinations. Keep LLM and persona decisions outside the backend.

## Preserve timing and evidence

State whether observation advances time. SSOS step 0 observes the initial state, and later steps advance supported backends before observation. Post-operation rows at the same step reflect operations without another physics advance. ROS2 observations are asynchronous and require startup telemetry; a missing storage reading must not be invented as zero.

Use kilograms internally for SSOS masses and liters for water volume; ROS2 translates upstream gram fields at the boundary. For cube, retain frozen timestep, controller timing, trial conditions, and stop criteria. A CPU/GPU comparison is valid only within its declared interval and tolerances.

## Backend replacement review sheet

| Concern | Question to answer in the change | Evidence to retain |
| --- | --- | --- |
| Units | Where are external values converted? | Boundary tests with nontrivial values |
| Clock | Does poll observe, advance, or wait? | Initial, pre-operation, and post-operation timing |
| Action completion | Does success mean admitted, scheduled, or completed? | Result plus measured later state |
| Failure handling | Can failed or busy equipment process work? | Rejection event and invariant checks |
| Missing readings | Is unknown different from zero? | Explicit missing/timeout result |
| Cleanup | Are failures/readers/processes reset after exceptions? | Failure-path regression |
| Candidate use | Does candidate execution construct the same backend? | Applied-input and evaluator consistency |
| Optional stack | Can discovery/CPU paths avoid unavailable dependencies? | Controlled absence tests |

Protocol details stay in the owning implementation: [scrubber](../scenarios/scrubber_degradation/implementation.md), [SSOS](../scenarios/ssos_eclss_loop/implementation.md), and [cube](../scenarios/balancing_cube/implementation.md). A replacement may require evaluator work when it emits different evidence; do not assume the old audit applies merely because telemetry has the same filename.

## Regression checks

Cover units, deterministic transitions, command success/rejection, failures, busy/capacity guards, cleanup, missing telemetry, and recorded state after operations. For plant changes, run mass-balance and invariant tests. For ROS2 changes, use adapter tests first, then the separately provisioned live suite. For MuJoCo changes, check native tests, GPU-unavailable behavior, and agreement tests in the correct optional environment.

Document any changed verification scope in both languages. A mock replacement proves orchestration; it does not inherit a physics backend's audit claim. See [change evaluation](change-evaluation.md) when the new evidence needs different checks.
