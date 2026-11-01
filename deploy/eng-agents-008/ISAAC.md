# Isaac development environment — 2026-10-23

Validation: [compact receipt](validation-20261023.json) and
[private checksummed logs/images](https://github.com/hirototamura/balancing-cube-simulation/releases/tag/isaac-development-20261023).
Engineering Agents: 1,187 passed / 4 skipped; One-Piece: 97 passed;
standalone simulator: 105 passed / 2 skipped plus 90 subtests; website build
and both Node test files passed. MJX/EGL, Blender OptiX, two Cartpole PPO
iterations, and the PhysX/CUDA/RTX camera probe passed on GPU 6.

Isaac Sim **6.2.0.0**, Isaac Lab **3.0.0**, PyTorch **2.11.0+cu130** and
RSL-RL **5.5.1** are installed in the workspace's `.runtime/isaac` (about 25 GB).
Python is **3.12.14**. The original `.venv` retains MuJoCo 3.3.7 and JAX 0.6.2.
No Docker, driver/kernel upgrade, reboot, or approval-setting change is needed.

## Install and launch

From `/home/one-piece/hiroto/Engineering Agents`:

```bash
bash engineering_agents/deploy/eng-agents-008/install-isaac.sh
# Only after you accept the NVIDIA Omniverse license:
export OMNI_KIT_ACCEPT_EULA=YES
nvidia-smi
# Free GPU 6 if Hermes is running. This does not stop vLLM on GPUs 0–5.
systemctl --user stop eng-agents-hermes-model.service
mkdir -p .runtime/isaac-runs
run=$(mktemp -d "$PWD/.runtime/isaac-runs/run-XXXXXXXX")
cd "$run"
bash ../../../engineering_agents/deploy/eng-agents-008/isaaclab.sh train \
  --rl_library rsl_rl --task Isaac-Cartpole --num_envs 16 --max_iterations 2 \
  physics=isaacsim_physx
systemctl --user start eng-agents-hermes-model.service
```

Always specify the physics backend: Lab's default can be Newton. The wrapper
selects the reserved GPU UUID, CUDA device 0, and Kit's `activeCudaGpus=0,` with
multi-GPU rendering disabled. Vulkan and CUDA ordinals differ; visibility alone
does not select the renderer. It refuses launch below 16,000 MiB free memory;
this check is not a scheduling lock. GUI/livestream configuration is not validated.

For a bounded PhysX/CUDA + RTX camera probe, from the workspace:

```bash
export CUDA_VISIBLE_DEVICES=GPU-8a14a4ef-ac77-553a-206d-55efbf82617b
export OMNI_KIT_ACCEPT_EULA=YES HEADLESS=1
# GPU 6 must be available. Choose a fresh output directory each time.
.runtime/isaac/bin/python engineering_agents/deploy/eng-agents-008/probe_isaac.py \
  .runtime/isaac-runs/camera-check-001
```

The probe requires changing finite CUDA joint state, GPU PhysX dynamics and
broadphase, and nonconstant finite RTX camera pixels. It writes JSON and PNG.
First launch may spend several minutes compiling shaders and downloading assets.
Run GPU checks from a host terminal or with approved host access: the Codex
sandbox cannot access the driver or bind the local sockets used by some tests.

## Dependency compatibility

The initial install followed NVIDIA's Isaac Lab 3.0 package instructions with
its release-tagged `uv-overrides.txt`. The final frozen set additionally pins
NumPy 2.3.1, packaging 26.0, fsspec 2026.2.0 and newton-usd-schemas 0.5.0 to
compatible Isaac Sim versions. The lock contains all 275 installed packages.

One upstream metadata conflict remains intentionally overridden: Isaac Lab
requires urllib3 >=2.8.0 while isaacsim-kernel pins 2.7.0. This setup uses 2.8.0,
consistent with NVIDIA's override. `uv pip check` reports that single conflict;
do not describe the environment as dependency-check clean or downgrade urllib3
without reassessing Lab. The installer uses the complete frozen list with
`--no-deps`; it checks existing installations without modifying them.

The host has Ubuntu 22.04, glibc 2.35, driver 595.84 and RTX A5000 24 GB cards.
Ubuntu 22.04 is currently supported but deprecated upstream. Headless display
warnings and a PCIe x4-versus-x16 link-width warning appeared during rendering;
the latter may limit throughput. No performance benchmark is claimed.

## Development sequence and limits

1. Confirm the cube's native MuJoCo/MJX behavior at the fixed timestep against
   the human-reviewed One-Piece requirements.
2. Import the lower-face three-wheel CAD into Isaac Sim with reviewed units,
   mass/inertia, joints, collisions, motor limits and sensor timing. STLs alone
   do not supply those physical properties.
3. Compare deterministic Isaac evaluations against the frozen reference;
   then build and train the cube's Isaac Lab task with separate evaluation seeds.

Installation tests cover Cartpole and small backend probes. They do not validate
cube CAD physics, numerical agreement for the cube, a trained cube policy, or
physical acceptance on any of the eight corners. CORE.md and historical evidence
remain unchanged. Native MuJoCo dynamics and CAD kernels remain CPU code.

Sources: [Isaac Lab installation](https://isaac-sim.github.io/IsaacLab/main/source/isaaclab/installation.html),
[Isaac Sim Python installation](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_python.html),
[system requirements](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html),
[NVIDIA license](https://docs.omniverse.nvidia.com/platform/latest/common/NVIDIA_Omniverse_License_Agreement.html).
