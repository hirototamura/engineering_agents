# Isaac cube exploration

Source review: [draft PR #85](https://github.com/hirototamura/engineering_agents/pull/85).
The [private evidence Release](https://github.com/hirototamura/balancing-cube-simulation/releases/tag/isaac-cube-20261024)
contains the 1.12 GB archive, videos, raw telemetry, paired comparisons and model
proposal traces. [isaac-cube-20261024.json](isaac-cube-20261024.json) records its
SHA-256, source commit and validation summary. The archive includes a per-file
checksum manifest; access requires the private simulator repository permission.

The user allocated physical GPUs 0–5 to Isaac simulation on 2026-10-23.
`ea-qwen-six-gpu-20261017.service` was stopped. GPU 6 retains the local proposal
model; GPU 7 is available for other work. Do not restart the retired vLLM service
without user direction. Check availability before every campaign.

This workflow exports the frozen `bottom-corner-000-20261017-3` One-Piece snapshot
through the existing bounded design compiler. It imports the resulting MJCF into
USD and selects its **physx** variant. It uses CUDA PhysX through Isaac Lab 3.0,
one process per GPU, with four rigid bodies, three reaction-wheel joints and eight
corner sphere colliders. Physics runs at 1 ms; control runs at 15 ms. Sensor noise
uses the same seeded stream as native MuJoCo; the controller receives delayed
tilt/gyro measurements. The symmetric torque-speed envelope and speed governor
are reapplied every physics step. All trial outcomes are retained.

The numerical frame is 166.235 mm; it does not assign unverified mass properties
to the separate 152 mm reference CAD. The first hardware configuration keeps
three lower-face wheels fixed in body coordinates. Eight-corner resets rotate
this same assembly; they do not relocate the wheels. Each supported corner's
COM direction defines upright. The new initial-condition distribution is an
exploration plan, not a human-adopted verification baseline.

## Commands

Run from the workspace containing the three repositories. Use a fresh output
directory for every command that writes evidence. NVIDIA's license acceptance
was explicitly supplied by the user for this installation.

Install Engineering Agents in the normal environment, and make its modules
available to the separate Isaac environment without replacing Isaac's pinned
dependencies. Run these installation commands from the workspace root:

```bash
.venv/bin/python -m pip install -e engineering_agents
.runtime/isaac/bin/python -m pip install --no-deps -e engineering_agents
```

The normal environment also needs the existing MuJoCo/One-Piece extras for export
and proposals, and SciPy for paired comparisons. The normal environment owns
`ea`; conversion and simulation use the explicit Isaac interpreter:

```bash
.venv/bin/ea isaac prepare export \
  --store one-piece/projects/balancing-cube/store --physics-only --output .runtime/isaac-cube/new-input
CUDA_VISIBLE_DEVICES=<allocated-GPU-UUID> OMNI_KIT_ACCEPT_EULA=YES \
  .venv/bin/ea isaac prepare convert --python .runtime/isaac/bin/python \
  .runtime/isaac-cube/new-input
.venv/bin/ea isaac prepare audit --python .runtime/isaac/bin/python \
  .runtime/isaac-cube/new-input
.venv/bin/ea isaac run campaign --python .runtime/isaac/bin/python \
  .runtime/isaac-cube/new-input --output .runtime/isaac-cube/new-campaign
.venv/bin/ea isaac analyze .runtime/isaac-cube/new-campaign
.venv/bin/ea isaac plot .runtime/isaac-cube/new-campaign
.venv/bin/ea isaac propose .runtime/isaac-cube/new-campaign \
  --output .runtime/isaac-cube/new-proposal
```

Use `ea isaac run pilot --python <isaac-python> INPUT --output NEW_RUN`
for the wiring pilot, or `ea isaac run batch --python <isaac-python> INPUT
--cases CASES.json --output NEW_SHARD` for one shard. Those operations require
`CUDA_VISIBLE_DEVICES` set to the allocated GPU UUID. The campaign runner selects
UUIDs itself after its existing allocation and occupancy checks.

`ea isaac plot RUN --kind pilot|trials|campaign` selects a figure explicitly;
otherwise the command detects the evidence type and rejects ambiguous inputs.
`ea isaac analyze CANDIDATE --reference REFERENCE --output comparison.json`
performs the existing paired comparison. Statistics and comparisons retain failed
trials and refuse incomplete/tampered evidence. Existing archived campaign source
keys remain readable; new manifests name the packaged batch worker explicitly.

`ea isaac --help` lists the five commands. Each operation also provides help,
for example `ea isaac prepare export --help` and `ea isaac run campaign --help`.
Use `python -m tools.cli` in place of `ea` when the console executable is not on
PATH. Runtime-specific modules under `environment.isaac` remain import-safe;
Isaac, CUDA, USD and plotting libraries load only when the selected operation
runs. There are no separate top-level Isaac Python scripts.

Export an accepted compiler-valid proposal with `--proposal`
and repeat import, audit, campaign and statistics. Matching campaign count/seed
reuses identical initial conditions and noise. Mechanical-only experiments keep
the saved controller unchanged. If both mechanics and control change, use the
existing four-cell comparison discipline. Fresh validation seeds are required
before claiming a selected design generalizes beyond exploration.
Supply previous measured comparisons with repeatable `--history <comparison.json>`
when proposing the next round, so regressions remain in the design context.

## Evidence obtained so far

`reference-24576-002` completed 24,576 six-second trials, 4,096 simultaneous
environments per GPU across GPUs 0–5, in 72.998 seconds including process startup
and output. This is a single measured campaign, not a repeated throughput
benchmark. Sampled peak device memory was 3,191 MiB on each simulation GPU.
Each corner has 3,072 seeded cases: tilt radius uniform 0–5 degrees, azimuth
uniform −pi to pi and yaw rate uniform −1 to 1 rad/s.

| Corner | Numerical screening pass fraction |
|---|---:|
| 000 | 1.0000 |
| 001 | 0.8747 |
| 010 | 0.8708 |
| 011 | 0.8740 |
| 100 | 0.8753 |
| 101 | 0.8701 |
| 110 | 0.8766 |
| 111 | 1.0000 |

The statistics reuse the pinned numerical screening gates. Completion alone does
not imply screening success. Wilson intervals describe sampling uncertainty
within this initial-condition distribution; they do not cover model error.

Engineering Agents' local Qwen model received the full measured statistics,
requirements, compiler bounds and comparison design. It proposed changing only
`side_m` to 0.18 m, predicting >95% screening success on the six weaker corners.
The compiler retained the exact saved controller. `candidate-24576-001` repeated
the identical plan and noise seeds in 73.191 seconds. Pass fractions fell to
79.46%, 79.20%, 79.59%, 80.05%, 78.35% and 79.88% for corners 001 through 110;
000 and 111 remained at 100%. There were 1,463 paired pass-to-fail regressions
and zero fail-to-pass improvements. The proposed improvement was falsified on
this exploration set. It is not an adopted design. Both campaigns retain all
49,152 episode outcomes and raw control-rate telemetry.

Changing side length also changes derived wheel radius, printed-frame mass and
inertias according to the existing compiler. It is one design variable, not an
isolated inertia-only experiment. The proposal's verbal mechanism does not
override these computed consequences.

Authored USD masses, principal inertias, COMs and topology match the exported
model. Eight corner-000 paired native MuJoCo runs **do not satisfy the existing
agreement limits**: angular-rate and wheel-speed differences exceed tolerances.
Consequently this PhysX backend remains **inconclusive for cross-backend
qualification**. Similar tilt traces do not establish solver interchangeability.
The complete qualification fixtures and physical parameter calibration remain
separate work. No physical acceptance, adopted baseline, or new requirement is
established by these results. No timestep refinement was used to adjudicate them.

The three-second `video-pilot-002/cube.mp4` shows an actual RTX-rendered PhysX
rollout with ideal sensing. Its accompanying telemetry is preliminary wiring
evidence. The large campaign includes delayed noisy sensing and contact gates;
do not describe the pilot video as a recording of those trials.

`video-eight-002/eight-corners.mp4` records a subsequent six-second rollout of
all eight corners using the batch evaluator's delayed noisy sensors, envelope,
contact sensing and stops. The mosaic labels each corner and actual measured
tilt; stopped trials continue falling with zero commanded effort. Metrics and
tilt plots use only observations through the recorded stop. This video uses
the same inertial/collision model with decorative geometry retained. It is a
separate eight-case demo, not a camera recording of all 24,576 trials.

The campaign manifest pins trial plans, source copies and GPU assignments.
Per-shard compressed telemetry contains every trial at every control tick,
including stopped-trial indices. Failed attempts remain in their own directories.
Store large evidence outside Git in checksummed private Release assets.

Source validation on 2026-10-24: **1,196 passed, 4 skipped** with
`pytest --ignore=tests/e2e`. The sandbox stalled in asynchronous thread-pool
tests; both affected tests passed immediately on the host, where the complete
suite then passed in 107.99 seconds. Nine new focused tests cover eight-corner
poses, native-compatible sensor noise and rejection of corrupt statistical
evidence. The final launcher additionally pins converted USD file hashes and
refuses assets modified during a campaign. Earlier large campaigns predate that
additional check; their archived asset bytes are pinned by the evidence pack.

## CLI consolidation validation (2026-10-28)

The twelve top-level Isaac scripts were replaced by the five `ea isaac`
commands. Physics/runtime code lives in `environment.isaac`, campaign/evidence/
proposal code in `scenario.balancing_cube`, and export/plotting/dispatch in
`tools.isaac`. No changes to the physics calculations, screening gates or
proposal bounds are intended by this refactor.

Local validation: 1,203 tests passed, four skipped (existing optional coverage),
and the ECLSS mock two-run proposal/reinjection smoke passed. Sixteen focused
Isaac/CLI tests cover lazy imports, argument/help routing, worker launch and
hashes, archived manifest compatibility, incomplete/tampered evidence, paired
regressions and a generated telemetry plot. These tests are included in the
mandatory cube CI job with its no-skips assertion. The refactored Isaac GPU
runtime has not been executed on the server; archived GPU measurements above
remain measurements of their original source revision.
