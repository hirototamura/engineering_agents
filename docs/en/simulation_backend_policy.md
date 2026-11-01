# Native MuJoCo and MJX execution policy

The user agreed to this direction on 17 October 2026. It describes future
campaigns. The current runner still executes native MuJoCo for each candidate
and adds MJX when requested. This document does not claim that selective
comparison is implemented or change completed experiment records.

## Terminology

Use **native MuJoCo–MJX agreement** or **implementation agreement** for the
comparison. Native MuJoCo and MJX are different simulation implementations.
CPU and GPU describe their execution hardware in these campaigns; hardware
labels alone do not identify the implementation being checked. Keep hardware
allocation, precision and utilization in execution metadata.

Existing record keys such as `numeric_gpu_verified`, `cpu_gpu_agreement`,
`mujoco_cpu` and `mjx_gpu` remain unchanged for compatibility. Presentation
labels can use the implementation names without rewriting historical JSON.

## Staged policy for future campaigns

1. **Qualify MJX within a declared scope.** Compare native MuJoCo and MJX on
   representative successful, failing and sensitive cases. Pin implementation
   versions, code, precision, model features, solver settings and the tested
   parameter envelope. Record observed discrepancies and qualification limits.
2. **Explore with MJX.** Run broad design exploration with the qualified MJX
   implementation. Identify MJX as the source of scores and gate decisions.
   An unpaired result is exploratory evidence, not an agreement result.
3. **Compare selectively.** Run paired native MuJoCo–MJX checks for finalists,
   cases near decision thresholds, relevant model features outside the
   qualified scope, and regression fixtures. Use the same resolved design,
   saved controller, initial state, disturbances, sampled noise and timing.
4. **Confirm the selection.** Confirm finalists with native MuJoCo and the
   declared paired checks before describing them as implementation-confirmed.
   Use the predeclared fresh conditions after selection. Preserve a failed or
   inconclusive result; do not infer which implementation is correct merely
   from its hardware or precision.

The execution policy shall record why each paired check was selected or omitted.
The execution policy shall mark an omitted comparison as `not_run`.
The execution policy shall not describe qualification as candidate-level
agreement for candidates that were not compared.
The execution policy shall retain the source implementation for every score.
The execution policy shall require requalification when a change invalidates
the recorded qualification scope.

Before the first run under this policy, implement and test the selective
execution path and pin a new One-Piece execution-policy revision. Existing
`--backend mjx_gpu` behavior is not an MJX-only exploration mode. Do not reuse
the completed October 17 study's execution-policy identity for a different
procedure. Fixed timestep, control timing, evaluation gates and saved-controller
rules remain unchanged; half-step adjudication is not introduced.

## Meaning of the evidence

Implementation agreement is a software and numerical consistency check.
Meeting simulation criteria is design verification within the model.
Physical validation requires measurements from the real cube. Neither
implementation is physical ground truth. Agreement can also confirm a shared
failure, and both implementations can share an incorrect model.
