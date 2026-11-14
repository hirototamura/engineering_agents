# Develop balancing cube

`balancing_cube` develops mechanical and control proposals for a reaction-wheel cube against revisioned One Piece inputs and deterministic numerical evidence. It is one engineering instance, alongside [scrubber](../scrubber_degradation/index.md) and [SSOS](../ssos_eclss_loop/index.md).

Use [implementation](implementation.md) to change SSOT resolution, compilation, design rounds, workflows, memory, or synchronization. Use [evaluation](evaluation.md) to change screening, aggregation, or numerical agreement. Public prerequisites, commands, and result interpretation belong to the [user guide](../../../users/scenarios/balancing_cube/index.md).

## Responsibility map

- `scenario_run.py`: configuration, required SSOT source, backend/mode choice, and design-loop construction.
- `design.py`: bounded mechanical/control compilation, dependent quantities, input digests, and trial matrices.
- `adapter.py`: frozen snapshot/reset, rollout orchestration, deterministic feedback, and retained incomplete evidence.
- `loop.py`: reference evaluation, proposal rounds, budgets, factorial comparisons, selection, and publication.
- `workflow.py` and `memory.py`: specialist handoffs, bounded prompt context, and evidence-linked episodes.
- `environment/mujoco`: native and MJX execution, model construction, contact, and control.
- `integrations/one_piece/mechanical_bridge.py`: exact input revisions, context projection, and durable delivery.

The normal scenario supports native MuJoCo CPU and MJX GPU paths. `isaac_*` modules and `environment/isaac` support separate conversion, campaign, and analysis work; Isaac is not a normal backend accepted by this scenario runner. Keep numerical-development evidence and any historical campaign claims separate.

The run requires an exact authoritative snapshot; there is no local-default fallback for its mission, model, requirements, or plan. Physical validation, electrical energy, and temperature prediction are not established by the current numerical loop.
