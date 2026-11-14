# Configure balancing cube

The bundled input is `src/scenario/balancing_cube/scenario.yaml`. It selects project `balancing-cube`, snapshot `cube.simulation.snapshot`, revision `bottom-corner-000-20261017-3`. Supply an existing One Piece store containing that revision through `--set ssot.path=/path/to/store`. The package does not restore or bundle the store.

## Install the required capabilities

From the prepared Python environment:

```bash
python -m pip install -e '.[mujoco,onepiece]'
```

The `onepiece` extra installs a pinned release wheel. Native CPU evaluation needs the MuJoCo extra. MJX needs the `gpu` extra and a compatible CUDA environment; use [developer setup](../../../developers/setup.md) for that environment. Isaac requires its separate runtime and conversion tools. The base quickstart installation alone is insufficient for normal cube execution.

## Select design mode and backend

`--backend mujoco_cpu` (alias `cpu`) is the default. `--backend mjx_gpu` (alias `gpu`) requests GPU comparison in addition to CPU screening. Missing required GPU evidence does not fall back to a claim of GPU verification.

`--design-mode none` evaluates the reference or an explicitly applied proposal. `llm` is the default and enables bounded proposal generation; `labeled_rule_base` is unsupported. The bundled LLM is Ollama with `llama3.2`, 30-second timeout, and 32768 context tokens. Configure the existing service using [LLM setup](../../guides/llm.md).

The default search is 5 rounds, at most 20 candidates, 1800 seconds, and 3 stagnant rounds. CLI budgets allow at most 20 rounds, 80 candidates, 7200 seconds, and 20 stagnant rounds. `iteration.proposal_retries` permits 0–3. Budgets are checked between CPU cases and around GPU batches; they do not interrupt an active solver/JIT call.

## Respect the frozen contract

CLI override roots are limited to `ssot`, `backend`, `agents`, `iteration`, `output`, and `memory`. Memory accepts `enabled` and `seed_runs`; iteration accepts the listed budget controls plus `enabled`. `workflow` settings present in the source YAML are not accepted as ordinary CLI overrides. Physics, thresholds, and seeds must change through an approved SSOT revision; `--seed` is rejected.

A normal design proposal changes only allowed design fields. Controller changes form a separate campaign, and simultaneous mechanical/controller changes need a 2×2 comparison. `--apply-proposals` accepts a direct proposal or a `design_proposals.json` with `selected_candidate`.

Outputs use the cube experiment track and require an empty/new directory. They are immutable evidence; [running](running.md) explains the workflow and [results](results.md) defines the metrics.

## Allowed design fields

These compiler bounds define the outer allowed range; the selected SSOT snapshot may tighten it.

| Field | Allowed range | Meaning |
| --- | --- | --- |
| `side_m` | 0.14–0.22 m | Cube side length |
| `print_mass_ref_kg` | 0.08–0.25 kg | Printed-frame reference mass before size scaling |
| `wheel_mass_kg` | 0.035–0.09 kg | Wheel mass parameter before motor-family rotor contribution |
| `wheel_radius_ratio` | 0.23–0.40 | Wheel radius / side length |
| `inner_radius_ratio` | 0.65–0.92 | Inner / outer wheel radius |
| `wheel_thickness_m` | 0.004–0.010 m | Wheel thickness |
| `tilt_q_scale`, `rate_q_scale`, `momentum_q_scale` | 0.25–4.0 | LQR Q-group multipliers; R is fixed |
| `yaw_rate_gain_nm_s` | 0–0.12 N·m·s | Yaw-rate damping gain |

The proposal must choose a registered motor family and provide all six mechanical fields, or use the special frozen reference. It cannot submit arbitrary controller K, change sensor assumptions, adjust timing, or lower gates. A geometrically in-range set can still fail clearance or inertia checks.

The original mechanical explanation makes one useful distinction: annular axial inertia depends on mass and radii, while thickness contributes to transverse inertia. A persuasive claim that thickness alone increased axial inertia at fixed mass/radii must be checked against the compiled model.
