# First trial: three lower mounting faces

The mission is balancing on each of the Cube's eight corners. The user clarified
this intent on 17 October 2026. The first development trial evaluates corner
`000` only. It does not establish performance on the other seven corners or in
hardware. Positioning the Cube between corners is still an unresolved operation.

## Model correction

The body frame starts at corner `(0,0,0)` and extends to `(s,s,s)`. The historical
model places wheel centers at `(s-inset,s/2,s/2)` and the two axis permutations.
These mounts are near the three faces opposite corner 000. The corrected first
trial uses `(inset,s/2,s/2)` and its permutations. These are the three faces
incident to the supporting corner. Wheel locations are fixed to the body;
they do not move when another corner is selected.

`physics.wheel_mount_side=near_corner_000` selects this model. Missing metadata
retains the historical `far_corner_000` behavior. Positive rotor-axis conventions,
rotor inertias, total mass, timing and numerical gates are unchanged. The new
field is a fixed configuration choice outside the six automatic mechanical
variables. Both native MuJoCo and MJX obtain their inertial bodies from it.
Only the modeled wheel/rotor bodies move. Fixed motor/stator and other masses
remain lumped into the frame, with its unchanged assumed COM and inertia.
This is not a calibrated mass-distribution model of the complete motor assemblies.

Moving the wheels lowers the combined center of mass. This does not establish
passive stability or guarantee better closed-loop performance: the inertia and
gravity coupling also change. Two rebuilt LQR alternatives were evaluated;
neither improved the delayed contact trials. A matched four-cell comparison separates placement and gain changes:
upper/old gains, upper/new gains, lower/old gains and lower/new gains. New runs
retain the 1 ms physics timestep and 15 ms control period, without half-step
adjudication. The retained historical controller passed 12/12 lower-face cases;
the new nominal LQR passed 9/12 and the reference-specific LQR passed 8/12.
The latest saved MASS controller also passed 12/12 with lower mounts and was
selected for the provisional first trial. Its score was 0.988586, compared with
0.991612 for its previous upper-mount result under the same development cases.
Lower center of mass did not improve that aggregate score. These disclosed
conditions are development evidence, not a fresh confirmation set.

## Versioned record and use

`cube.simulation.snapshot@bottom-corner-000-20261017-3` pins the corrected model,
the retained MASS saved K, a lower-face descendant of `D-000544-52890`, and the
English requirement drafts. Its first-trial scope is explicit. `M-VERTEX` retains
the eight-corner mission. Requirement wording remains draft; the source intent
is the user's clarification. No adopted baseline or old result is overwritten.
`controller_design_snapshot_ref` identifies the historical nominal plant used
to generate the retained controller. The bridge resolves that exact record.
Subsequent Q edits keep this declared plant; missing Q settings inherit the
saved design parameters. Repeating those settings preserves K bit for bit.
The MASS study records are required to resolve the exact controller source.
The model's inherited `revision` string identifies its legacy source; the exact
simulation-snapshot reference identifies the new authoritative configuration.

Replay renderers now use the declared mounting side and inset. Some historical
memory-report drawings used approximate hardcoded wheel locations; those views
are not authoritative geometry. Original HTML remains archived. The maintained
renderers use model metadata for newly generated reports.

The normal Cube scenario defaults to this new snapshot. Historical reproduction
must explicitly select its original snapshot and archived evaluator source.
The snapshot preparation tool refuses an already prepared revision; retry its
saved `records.json` import instead. Numerical evidence on the first corner
does not verify the eight-corner hardware requirement.

The standalone simulator defaults to `config/first_trial_bottom.json` and a new
output folder. It rebuilds its own ideal-pivot preview controller; that preview
does not establish performance in delayed contact trials. Its preserved
`config/reference.json` reproduces the old geometry.

## Compute allocation

Qwen uses physical GPUs `0,1,2,3,4,5` through three data-parallel replicas, each
with tensor-parallel size 2. MJX uses GPUs `6,7`. Native MuJoCo uses CPUs.
The model revision is pinned. This layout adds concurrent serving capacity;
it does not imply a sixfold improvement in single-request latency. vLLM documents
the combined [data-parallel and tensor-parallel deployment](https://docs.vllm.ai/en/stable/serving/data_parallel_deployment/).

`scripts/serve_qwen_six_gpu.sh` validates disjoint physical device lists before
launch. The current deployment is a transient user systemd service, not a boot
startup configuration. Its previous launcher and rollback command are preserved
on the server. See [simulation execution policy](simulation_backend_policy.md)
for staged implementation checks; this geometry change does not implement
MJX-only exploration or selective comparison in the design-loop runner.
