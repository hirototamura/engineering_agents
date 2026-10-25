---
name: cube-mechanical-mass-uncertainty
description: "Compute balancing-cube mass, CoM, inertia tensor and bounded uncertainty from part masses, frames and primitive or CAD tensors. Use for mass-property budgets and sensitivity; do not infer missing masses or print infill."
---

# Cube Mechanical Mass Uncertainty

Use this skill when wheel placement, battery placement or uncertain part masses can move the cube's mass distribution.

Obtain exact configuration references and part frames from One-Piece/CAD records. Use SI units. `center_m` is already in the common body frame; `rotation_local_to_body` rotates only the part's local inertia tensor. Primitive cylinder axes are local Z. CAD tensors are about the part CoM, with `reference_mass_kg`; the tool rescales them when mass changes at fixed geometry.

The tool applies rotation and the parallel-axis theorem, reports principal moments, and states the inertia/product-of-inertia sign convention. Unknown mass is **null**, not zero: the known-parts subtotal is available, while the full system remains unresolved. Do not assign PLA to purchased-part envelopes or equate slicer infill percentage with whole-part density.

Uncertainty uses independent uniform bounded mass/position inputs and a fixed random seed. Its central 95% sample range is neither a worst-case envelope nor a confidence interval. Correlated errors, uncertain geometry and flexible-body modes require a different model. Preserve the nominal results and the assumptions used for every uncertainty result.

## Execute

Hermes is the harness. Use its terminal tool to execute the trusted Engineering Agents calculator, then read `summary.json`, `receipt.json` and the generated plots. `result.json` retains full arrays. The LLM explains and proposes; the calculator determines numerical results.

From the Engineering Agents checkout (`EA_ENGINEERING_REPO` in the deployed wrapper):

```bash
ea-engineering run mechanical \
  --input skills/engineering/cube-mechanical-mass-uncertainty/examples/input.json \
  --output experiments/balancing_cube/engineering_analysis/NEW_RUN_ID/mechanical
```

The bundled input is an assumed example, not a measured cube or an approved design. Copy it to a new run input and replace the values with source-linked data.

Read summaries with `cat summary.json receipt.json`; no ad hoc Python/heredoc formatter or approval-setting change is needed.

Use a fresh output path. Failures leave an input and failure receipt; do not overwrite evidence or modify the tool to force a pass. Read [validation.md](references/validation.md) before claiming this skill is qualified. Read the scope/limitations in the machine result when reporting conclusions. State data gaps and the next discriminating measurement.
