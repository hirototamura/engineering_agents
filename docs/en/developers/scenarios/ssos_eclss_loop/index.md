# Develop the SSOS ECLSS loop

`ssos_eclss_loop` coordinates storage observations and life-support operations with distinct runtime actors and post-run designers. It is one engineering instance, alongside [scrubber](../scrubber_degradation/index.md) and [balancing cube](../balancing_cube/index.md). Its domain is not the framework's universal data model.

Use [implementation](implementation.md) for lifecycle, proposal application, agent/backend wiring, and failure boundaries. Use [evaluation](evaluation.md) for the persisted scorecard, physics audit, integrity, and candidate selection. Existing configuration and commands belong to the [user guide](../../../users/scenarios/ssos_eclss_loop/index.md).

## Responsibility map

- `scenario_run.py`: resolved inputs, proposal consumption, backend construction, operation/survival ordering, evidence, and post-run design.
- `agent_config.py` and `scenario/agents`: independent actor/design modes and their teams/designers.
- `design_tools.py`, `design_variables.py`, `design_constraints.py`, `design_proposals.py`, and `design_eval.py`: sizing, constraints, candidate simulation, proposal translation, and selection.
- `evaluation.py`, `physics_gate.py`, `integrity_guard.py`, and `unified_evaluation.py`: measured evaluation and admissibility.
- `scenario/jobs/iterate.py`, `chain_memory.py`, and `chain_selection.py`: applied-design chains, compact history, and selection among flown machines.
- `environment/ssos/eclss`: storage/action boundary, mock, plant model, ROS2 adapters, and units.

The supported backends have different purposes: loop mock for operation orchestration, plant simulation for its model physics and scorecard, ROS2 for live SSOS operations. The plant scorecard is not applicable to mock/ROS2 runs. Graph rewiring and hardware capacity changes also have different backend applicability; see [user configuration](../../../users/scenarios/ssos_eclss_loop/configuration.md).

A design proposal and an approved, admissible, simulated final design are different states. Manual proposal adoption has known status/bounds limitations described in [implementation](implementation.md); do not infer a universal hard gate from final-selection labels.
