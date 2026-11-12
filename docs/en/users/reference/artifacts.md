# Artifact reference

The output directory is the unit of evidence. Retain it together with the repository revision and relevant external input revisions. File presence alone does not establish a successful or valid result.

## Common inspection roles

- `summary.json`: a completed run's compact conditions, measurements, status, and paths. Its schema is scenario-specific.
- Saved configuration or SSOT input records: what the run actually used, including applied changes.
- `telemetry.jsonl` and event records: observations and actions in the scenario's units and time convention.
- `design_proposals.json`: proposed future changes, when a designer ran. Its schema and application rules belong to the scenario.
- Evaluation and report files: deterministic checks plus derived human-readable views. Read applicability and validity before totals.

Streams are written when used; not every run has every file. A proposal can be empty or absent, and evaluation can be not applicable or incomplete. The framework does not impose one universal pass/fail schema across the three scenarios.

## Find the owning contract

[Scrubber results](../scenarios/scrubber_degradation/results.md) defines its telemetry, recovery indicators, messages, and recommendation limits. [ECLSS results](../scenarios/ssos_eclss_loop/results.md) defines canonical telemetry rows, evaluation schema, physics/integrity gates, consumed proposals, and chain evidence. [Cube results](../scenarios/balancing_cube/results.md) defines immutable design, screening, validation, proposal, and synchronization records.

ECLSS chains add `chain_summary.json`, `chain_final_answer.json`, numbered simulation directories, and optional paired replays. These are distinct from one run's summary. A `job run` input is an execution specification, not a verification report.

The [report library](../guides/reports.md) indexes HTML files and can create translated views and thumbnails. Those derived files aid inspection; the original numeric and condition records remain the evidence to cite.

For retention, storage internals, and artifact synchronization changes, see the [developer storage reference](../../developers/reference/storage.md).

## What each record can prove

| Record family | Supports | Does not prove by itself |
| --- | --- | --- |
| Configuration / frozen snapshot | Input identity and declared conditions | Correct execution |
| Telemetry / case records | Observed model behavior | Requirements passed |
| Events / command results | What was attempted, accepted, or rejected | A later change caused an improvement |
| Deterministic evaluation | Results under a declared evaluator | Physical fidelity |
| Agent messages / hypotheses | Why a proposer chose an experiment | Truth of the proposed mechanism |
| Proposal / selection | Intended next design and selection rationale | That every proposed field was re-simulated |
| Provenance / delivery receipt | Traceability and publication state | Engineering acceptance |

For comparison, retain both the input and evaluation layers. An isolated score or image omits the conditions needed to interpret it.
