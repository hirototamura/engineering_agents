# Eng Agents 008: reproducible development handover

This transfers the local Engineering Agents development state to
`gpu-sv-008:/home/one-piece/hiroto/Engineering Agents`. The Codex project is
**Eng Agents 008**. GitHub holds source revisions; a private Release holds large
evidence files. This is development infrastructure, not a new design iteration.

The [Isaac development setup](ISAAC.md) adds an isolated Isaac Sim 6.2 / Isaac
Lab 3.0 environment for the next CAD and reinforcement-learning stage. It retains
the pinned MuJoCo/MJX runtime below. Installation smoke tests do not replace the
cube's deterministic MuJoCo/MJX confirmation or physical acceptance.

The [eight-corner Isaac cube workflow](ISAAC-CUBE.md) documents the subsequent
GPU 0–5 allocation, 24,576-trial campaigns and bounded proposal evaluation.

## Source and evidence

The original handover snapshots remain on
`codex/eng-agents-008-handover-20261022`. Current source maintenance continues in
Engineering Agents #82 and One-Piece #12. Use `workspace.lock.json` for exact
companion revisions instead of assuming that every branch has advanced together:

- [Engineering Agents](https://github.com/hirototamura/engineering_agents/pull/82): experiment orchestration, bounded proposals, simulation adapters, reports and Astro website.
- [One-Piece](https://github.com/hirototamura/one-piece/pull/12): reviewed system model, requirements, canonical JSON, requirements explorer and evidence retrieval.
- [Cube simulator](https://github.com/hirototamura/balancing-cube-simulation/tree/codex/eng-agents-008-handover-20261022): standalone simulation, lower-wheel configuration and reference CAD builders.
- [Private handover Release](https://github.com/hirototamura/balancing-cube-simulation/releases/tag/handover-20261022): run data, One-Piece evidence objects, bilingual reports, CAD/STL/BOM inputs and website assets. GitHub access to the private simulator repository is required.

`workspace.lock.json` pins companion commits and runtime/model revisions.
`evidence-manifest.json` pins all seven Release asset hashes. The Engineering
Agents commit that contains these files defines the remaining source revision;
save that full SHA with every new experiment. No existing PR was merged.

Generated website CAD assets remain outside Git. Website builds now restore the
hash-pinned, already public CAD package automatically (see `website/README.md`).
The historical private `website-cad` handover pack remains available for offline
restoration. Without either package, the CAD pages will
be absent. The private pack also retains original downloaded archives so report
download links continue to resolve. Mac-only absolute `file:` links in historical
reports remain historical; use workspace-relative file paths on Linux.

Credentials, local caches, virtual environments, disposable SQLite indexes and
presentation work are excluded. One-Piece now owns the requirements explorer;
the local `requirements-explorer-site` checkout is a preserved prototype copy.
See `one-piece/docs/en/requirements_explorer.md` for the pinned-model builder.
Presentation work and the other local folders remain local at the user's request.

Historical `integration-validation` data is indexed in
`one-piece/datasets/integration_validation_20261024.json`. Retrieve selected runs
and acceptance receipts with `onepiece datasets list/fetch/verify`; see
`one-piece/docs/en/dataset_storage.md`. New archives use the private simulator
Release `validation-archive-20261024`; exact existing Release assets are reused
by SHA-256. This catalog is optional during workspace setup so a development
checkout does not download all historical validation files.

Experiment outputs now live under `engineering_agents/experiments/eclss/` or
`engineering_agents/experiments/balancing_cube/`. The importer translates old
Release paths during restoration without changing the archived bytes or hashes.
Recorded `summary.scenario` selects the track, including ECLSS smoke runs whose
folder names mention cube-related work. Unknown tracks stop for explicit
classification. Existing edited destination files remain protected.

## Recreate on another environment

Install GitHub CLI and authenticate as yourself (`gh auth login`). Do not copy
another environment's tokens. Clone Engineering Agents at this handover revision
and run the importer from its checkout:

```bash
mkdir -p "$HOME/hiroto/Engineering Agents"
cd "$HOME/hiroto/Engineering Agents"
gh repo clone hirototamura/engineering_agents -- --branch codex/eng-agents-008-handover-20261022
# For a frozen reproduction, git checkout the full handover commit SHA here.
python3.12 engineering_agents/deploy/eng-agents-008/restore_workspace.py "$PWD"
bash engineering_agents/deploy/eng-agents-008/install-runtime.sh
cp engineering_agents/deploy/eng-agents-008/workspace_agents.md AGENTS.md
```

The importer verifies SHA-256, rejects archive traversal/symlinks, preserves
existing changed files, and refuses to reset a different companion checkout.
It does not pull or overwrite ongoing work. Create a `codex/<task>` branch in
the relevant repository before development. Push reviewed commits to GitHub,
then explicitly fetch them in other environments. Do not use shared writable
worktrees or repeatedly copy a whole home directory between machines.

The runtime installer uses user-space environments and a separate CUDA build
prefix without spaces. It requires `uv` 0.12.5 and standard Linux build tools.
The installed dependency set is pinned in `development-linux-py312.txt` and
`cuda-build-linux64.lock`; Hermes uses its upstream frozen `uv.lock`.

## Hermes and the local model

Hermes **v0.22.4**, commit `4d04303818b61bf3aa09278af48356315515965b`, uses a
dedicated `HERMES_HOME` under `.runtime/hermes-home`. The selected model is
**Qwen3.8-27B Q4_K_M**, published by ggml-org from Qwen's Apache-2.0 model.
Its 18,973,870,528-byte quantized file leaves memory for a bounded context on one
24 GB card. This is a quality-oriented coding choice, not a claim that a universal
best model has been established by project-specific benchmarks. Quantization
can reduce quality; model/tool smoke tests are not a coding benchmark.

Inference uses llama.cpp **b11819**, CUDA **12.8.1**, compiled for **sm_86**.
The publisher's current Linux prebuilt binary required newer glibc than this
Ubuntu 22.04 host, so this installation builds from source instead of modifying
the OS. The server binds to **127.0.0.1:8016**, uses one slot and a 65,536-token
context, and explicitly requests CUDA for all model layers. Automatic memory
fitting is disabled; the launcher does not fall back to a cloud provider.

```bash
ssh gpu-sv-008
cd '/home/one-piece/hiroto/Engineering Agents'
# Start in a separate terminal if the user service is not running:
bash engineering_agents/deploy/eng-agents-008/start-model.sh
# Interactive development agent:
bash engineering_agents/deploy/eng-agents-008/hermes.sh
# One bounded task:
bash engineering_agents/deploy/eng-agents-008/hermes.sh chat --oneshot \
  --max-turns 8 -q 'Read AGENTS.md and explain the three repositories. Do not modify files.'
```

The installed user service is `eng-agents-hermes-model.service`:

```bash
systemctl --user status eng-agents-hermes-model
systemctl --user start eng-agents-hermes-model
systemctl --user stop eng-agents-hermes-model
journalctl --user -u eng-agents-hermes-model -n 50
# Recreate this service on another environment after runtime installation:
.venv/bin/python engineering_agents/deploy/eng-agents-008/install_model_service.py
```

This service is enabled for user login. System linger is disabled on the shared
host, so automatic startup before login is not promised. A start verifies the
19 GB model checksum before loading; allow time for that check. Do not run a
second launcher while the service is already using the selected GPU.

Hermes runs with the **local terminal backend**, as the user opted out of
OpenShell to avoid rebooting the shared host. This is not an isolated sandbox.
Existing host permissions and Hermes approval prompts apply; no `--yolo` mode
is configured. Do not expose the model or Hermes management services publicly.
OpenShell 0.1.5 binaries were downloaded and verified but are inactive. No Docker
installation, kernel upgrade, reboot, or existing model-server restart was made.

GPU 6 is selected by UUID `GPU-8a14a4ef-ac77-553a-206d-55efbf82617b`.
GPUs 0–5 retain the existing service; GPU 7 is untouched. On another host set
`EA_GPU_UUID` and `EA_EGL_DEVICE_ID` to the appropriate available GPU. These
settings do not reserve resources against other users; check `nvidia-smi` before
launching expensive workloads. A 27B model occupies most of one A5000: large
MJX batches or CAD renders may require stopping this new model service first.

## Acceleration and validation

The wrapper sets CUDA device visibility, `JAX_PLATFORMS=cuda`,
`MUJOCO_GL=egl`, and `PYOPENGL_PLATFORM=egl`. CUDA inference and MJX, NVIDIA
EGL/OpenGL rendering, and Blender Cycles OptiX are distinct accelerated paths.
Native MuJoCo dynamics, CAD kernels, orchestration, tokenization and I/O still
use CPU code. Do not describe those as GPU-accelerated just because a GPU exists.

```bash
export CUDA_VISIBLE_DEVICES=GPU-8a14a4ef-ac77-553a-206d-55efbf82617b
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl MUJOCO_EGL_DEVICE_ID=6
export JAX_PLATFORMS=cuda XLA_PYTHON_CLIENT_PREALLOCATE=false
.venv/bin/python engineering_agents/deploy/eng-agents-008/probe_acceleration.py mjx .runtime/validation
.runtime/graphics/bin/python engineering_agents/deploy/eng-agents-008/probe_acceleration.py optix .runtime/validation
```

Both probes fail if the requested NVIDIA backend is unavailable. The MJX probe
steps a small falling-body model, transfers its resulting state for EGL rendering,
and records vendor/renderer strings. The OptiX probe renders a small scene and
records its selected device. Neither is a physical cube acceptance test.

Local handover checks: Engineering Agents 1,180 passed / 5 skipped; One-Piece
97 passed; standalone simulator 116 passed / 8 skipped plus 97 subtests;
website build and four tests passed. Six additional archive-import tests check
idempotency, changed-file preservation, traversal and symlink rejection.

Remote Linux validation also passed: Engineering Agents 1,187 passed / 4 skipped,
One-Piece 97 passed, and the restored website built with four passing tests using
Node.js 22.23.2. GPU probes recorded NVIDIA RTX A5000 for both EGL/OpenGL and
OptiX and `cuda:0` for MJX under the reserved GPU UUID. Local CUDA device 0 here
means the sole visible card, physical GPU 6.

The final Hermes trial succeeded with three real terminal calls (`pwd`, listing
the workspace, reading AGENTS.md), then correctly described all three repository
roles. It used 16,760 total reported tokens and completed in 24.5 seconds. With
the supported 65,536-token context, GPU 6 used 20,421 MiB; GPUs 0–5 kept their
existing allocations and GPU 7 remained idle. See `validation-20261022.json` for
the compact receipt. Detailed validation logs are in `eng-agents-validation-20261022.zip`
on the private handover Release. This verifies integration, not autonomous coding
quality or a full engineering design iteration.

## Sources

- [Hermes source release](https://github.com/NousResearch/hermes-agent/tree/v0.22.4)
- [Qwen3.8-27B model card](https://huggingface.co/Qwen/Qwen3.8-27B)
- [Pinned quantized model](https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF/tree/a316ea527fde32c12487be7574e2db5ac2ad2a7e)
- [llama.cpp b11819](https://github.com/ggml-org/llama.cpp/tree/b11819)
- [OpenShell kernel requirements](https://docs.nvidia.com/openshell/latest/about/support-matrix): current host reports Landlock ABI 1; current OpenShell requires ABI 3. OpenShell is deferred, not silently downgraded.
