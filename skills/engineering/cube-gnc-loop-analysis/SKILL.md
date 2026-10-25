---
name: cube-gnc-loop-analysis
description: "Analyze a balancing-cube tilt-axis plant: transfer function, Bode response, sampled pole placement and saturated nonlinear response. Use for local control feasibility and gain-study diagnostics, not automatic production gain changes."
---

# Cube Gnc Loop Analysis

Use this skill to test whether a proposed local tilt-axis feedback law is plausible before a full three-axis MuJoCo study.

Read the versioned One-Piece model and identify the corner, mass, CoM height, pivot inertia, torque convention and control period. Keep measured, assumed and derived inputs distinct. If these inputs are unavailable, label the result as a sensitivity study; do not infer a validated plant from a successful controller fit.

The tool uses `J θ̈ + d θ̇ − m g h θ = u_body`. The input is **body torque**; ideal wheel motor torque has the opposite sign. It linearizes about upright equilibrium, places two continuous poles, checks the sampled closed-loop poles, and compares a zero-order-held linear response with a torque-limited nonlinear response. The Bode plot is for an **unstable open-loop plant**. Do not report classical phase/gain margins as a proof of stability.

Use the full three-axis simulator for wheel momentum, contact, yaw, estimator error and finite wheel speed. This skill does not change the saved controller K, campaign conditions, requirements or accepted baseline. A local result is development evidence, not compliance with the hardware hold requirement.

## Execute

Hermes is the harness. Use its terminal tool to execute the trusted Engineering Agents calculator, then read `result.json`, `receipt.json` and the generated plots. The LLM explains and proposes; the calculator determines numerical results.

From the Engineering Agents checkout (`EA_ENGINEERING_REPO` in the deployed wrapper):

```bash
python -m tools.engineering_skills run gnc \
  --input skills/engineering/cube-gnc-loop-analysis/examples/input.json \
  --output experiments/balancing_cube/engineering_analysis/NEW_RUN_ID/gnc
```

The bundled input is an assumed example, not a measured cube or an approved design. Copy it to a new run input and replace the values with source-linked data.

Use a fresh output path. Failures leave an input and failure receipt; do not overwrite evidence or modify the tool to force a pass. Read [validation.md](references/validation.md) before claiming this skill is qualified. Read the scope/limitations in the machine result when reporting conclusions. State data gaps and the next discriminating measurement.
