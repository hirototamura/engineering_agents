# Choose a scenario

Each bundled scenario is a complete instance with its own system, design space, actions, metrics, and verification limits. Choose by the question you want to investigate.

## Scrubber degradation

[Scrubber degradation](scrubber_degradation/index.md) studies a degrading CO₂ scrubber and recovery operations in a small station model. Compare no agents, labeled rules, and LLM agents; inspect CO₂ and power-margin recovery. Post-run design recommendations are emitted but are not automatically applied to a later simulation.

## ECLSS operations and capacity design

[ECLSS loop](ssos_eclss_loop/index.md) operates air revitalization, oxygen generation, and water recovery. Select a local mock, local plant model, or ROS2 SSOS backend. It supports proposal application and design chains; the plant model provides survival and resource/cost/mass evaluation.

## Balancing cube

[Balancing cube](balancing_cube/index.md) evaluates mechanical designs against frozen One Piece requirements. It separates candidate screening, CPU/GPU numerical validation, and optional Isaac campaigns. It needs an existing SSOT store and optional simulation dependencies; physical validation remains outside the shipped evidence.

The [quickstart](../quickstart.md) selects ECLSS mock solely to demonstrate a local design handoff. To implement another domain, follow [developer scenario guidance](../../developers/guides/add-scenario.md); external scenario loading is not implemented.
