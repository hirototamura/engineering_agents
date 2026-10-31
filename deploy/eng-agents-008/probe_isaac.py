"""Bounded Isaac Sim PhysX/CUDA + RTX camera smoke; not cube acceptance."""
from __future__ import annotations

import argparse
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys

GPU = "GPU-8a14a4ef-ac77-553a-206d-55efbf82617b"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if os.environ.get("CUDA_VISIBLE_DEVICES") != GPU:
        raise RuntimeError(f"Set CUDA_VISIBLE_DEVICES={GPU}")
    args.output.mkdir(parents=True, exist_ok=False)
    import torch
    import warp as wp

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("Exactly one CUDA GPU is required; no CPU fallback")
    properties = torch.cuda.get_device_properties(0)
    if str(properties.uuid).removeprefix("GPU-").lower() != GPU.removeprefix("GPU-").lower():
        raise RuntimeError(f"Unexpected GPU UUID: {properties.uuid}")

    import gymnasium as gym
    import isaaclab_tasks  # noqa: F401 -- register packaged tasks
    from isaaclab.app import launch_simulation
    from isaaclab_tasks.utils.hydra import resolve_task_config

    # Explicitly select Isaac Sim, rather than the Lab default Newton backend.
    sys.argv = [sys.argv[0], "physics=isaacsim_physx", "renderer=isaacsim_rtx", "presets=rgb"]
    cfg, _ = resolve_task_config("Isaac-Cartpole-Camera", "")
    cfg.scene.num_envs = 1
    cfg.sim.device = "cuda:0"
    cfg.seed = 42
    launcher = {"device": "cuda:0", "headless": True, "visualizer": [],
                "multi_gpu": False,
                "kit_args": "--/renderer/multiGpu/enabled=false --/renderer/multiGpu/activeCudaGpus=0,"}
    with launch_simulation(cfg, launcher):
        env = gym.make("Isaac-Cartpole-Camera", cfg=cfg)
        try:
            env.reset()
            robot = env.unwrapped.scene["robot"]
            initial_joints = wp.to_torch(robot.data.joint_pos).clone()
            with torch.inference_mode():
                for _ in range(16):
                    env.step(torch.zeros(env.action_space.shape, device="cuda:0"))
            joints = wp.to_torch(robot.data.joint_pos)
            if joints.device.type != "cuda" or not torch.isfinite(joints).all():
                raise RuntimeError("PhysX did not return finite CUDA joint state")
            joint_change = float((joints - initial_joints).abs().max())
            if joint_change <= 1e-6:
                raise RuntimeError("Cartpole dynamics did not advance")
            import omni.usd

            scene = omni.usd.get_context().get_stage().GetPrimAtPath("/physicsScene")
            gpu_dynamics = scene.GetAttribute("physxScene:enableGPUDynamics").Get()
            broadphase = scene.GetAttribute("physxScene:broadphaseType").Get()
            if gpu_dynamics is not True or broadphase != "GPU":
                raise RuntimeError(f"GPU PhysX is inactive: {gpu_dynamics}, {broadphase}")
            camera = env.unwrapped.scene["tiled_camera"]
            pixels = camera.data.output["rgb"][0]
            if pixels.device.type != "cuda" or not torch.isfinite(pixels).all():
                raise RuntimeError("Camera did not return finite CUDA pixels")
            if pixels.max() <= pixels.min():
                raise RuntimeError("Camera returned a constant image")
            from PIL import Image

            Image.fromarray(pixels.cpu().numpy()).save(args.output / "isaac-rtx.png")
            result = {
                "passed": True, "task": "Isaac-Cartpole-Camera", "steps": 16,
                "gpu_uuid": GPU, "device": str(pixels.device), "gpu_name": properties.name,
                "physics_config": type(cfg.sim.physics).__module__ + "." + type(cfg.sim.physics).__name__,
                "renderer": camera.cfg.renderer_cfg.renderer_type,
                "image_shape": list(pixels.shape),
                "pixel_min": int(pixels.min()), "pixel_max": int(pixels.max()),
                "physics_gpu_dynamics": gpu_dynamics, "physics_broadphase": broadphase,
                "max_joint_position_change": joint_change,
                "versions": {p: version(p) for p in ("isaacsim", "isaaclab", "torch", "rsl-rl-lib")},
                "physical_validation": False, "cube_cad_validation": False,
            }
            if result["renderer"] != "isaac_rtx" or "isaaclab_physx" not in result["physics_config"]:
                raise RuntimeError(f"Unexpected backend: {result}")
            (args.output / "isaac.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result), flush=True)
        finally:
            env.close()


if __name__ == "__main__":
    main()
