---
name: cube-electrical-wheel-power
description: "Assess reaction-wheel motor current, voltage headroom, operating-mode energy and winding heat using an effective-DC model. Use for actuator/driver power budgets; not for direct hardware actuation or unqualified BLDC phase constants."
---

# Cube Electrical Wheel Power

Use this skill to check whether the wheel drive can deliver the torque/speed requested by a controller and what that costs electrically.

Collect motor torque/back-EMF constants, effective winding resistance, driver current/duty limits, minimum bus voltage, thermal parameters and the ordered operating modes. Convert BLDC phase/line/RMS/peak conventions to a documented **effective-DC** equivalent first. SI torque and back-EMF constants shall agree in this model. A datasheet label alone does not establish that conversion.

The tool computes `I=τ/Kt`, `V=Ke ω+R I`, copper loss, electrical/mechanical power, driver losses, battery energy and a first-order winding temperature. Modes are a time sequence and share the preceding winding temperature. An infeasible current, voltage or temperature is flagged; the requested torque is not treated as achieved.

Leave regeneration disabled unless both driver and battery charging capability are verified. Braking energy otherwise goes to a dissipative path; do not credit it to battery capacity. The model excludes voltage sag, temperature-dependent resistance, switching ripple and iron/friction losses. It sends no actuator commands and cannot qualify a real driver or battery.

## Execute

Hermes is the harness. Use its terminal tool to execute the trusted Engineering Agents calculator, then read `result.json`, `receipt.json` and the generated plots. The LLM explains and proposes; the calculator determines numerical results.

From the Engineering Agents checkout (`EA_ENGINEERING_REPO` in the deployed wrapper):

```bash
ea-engineering run electrical \
  --input skills/engineering/cube-electrical-wheel-power/examples/input.json \
  --output experiments/balancing_cube/engineering_analysis/NEW_RUN_ID/electrical
```

The bundled input is an assumed example, not a measured cube or an approved design. Copy it to a new run input and replace the values with source-linked data.

Use a fresh output path. Failures leave an input and failure receipt; do not overwrite evidence or modify the tool to force a pass. Read [validation.md](references/validation.md) before claiming this skill is qualified. Read the scope/limitations in the machine result when reporting conclusions. State data gaps and the next discriminating measurement.
