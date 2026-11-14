# Develop scrubber degradation

`scrubber_degradation` exercises a team responding to CO₂-removal degradation and reduced power margin in a mock station. It owns recovery commands, health classification, event provenance, and a post-run permanent-design proposal. It is one bundled instance, alongside [SSOS](../ssos_eclss_loop/index.md) and [balancing cube](../balancing_cube/index.md).

Use [implementation](implementation.md) when changing simulator coupling, the step team, command handling, or evidence. Use [evaluation](evaluation.md) when changing health bands, recovery timing, or summary semantics. For existing settings and run procedures, use the [user guide](../../../users/scenarios/scrubber_degradation/index.md).

## Responsibility map

- `scenario/scrubber_degradation/scenario_run.py`: effective configuration, output preparation, loop ordering, summary, proposal persistence, and provenance export.
- `scenario/agents/scrubber_degradation_team.py`: deliberation, recovery recommendations, application through the simulator, and post-run proposal generation.
- `environment/scrubber`: mock ECLSS model, operations, design state, anomaly handling, and the station facade coupling EPS.
- `environment/protocol.py`: scrubber-oriented telemetry, health, command, topology, and simulator boundary types.

The runner supports no-agent, labeled-rule, and LLM teams through its configuration. EPS can be mock or ROS-backed; that does not replace the mock ECLSS plant with SSOS. Do not transfer SSOS storage units or scorecards into this scenario without a deliberate contract change.

## Current limit

The run writes `design_proposals.json` when a team proposes a permanent change, but the executor does not apply scrubber proposals to the next simulation. A dashboard before/after preview is not re-simulation evidence. Closing that loop needs explicit proposal validation/application, recorded consumed inputs, a second independent run, and regression coverage before the documentation can claim it is implemented.
