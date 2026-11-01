"""Native CPU and explicitly requested MJX GPU rollouts at a fixed timestep.

JAX/MJX is imported only by the GPU function. There is no CPU fallback that can
be mistaken for GPU evidence and no timestep refinement in this integration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class MechanicalTelemetry:
    time_s: float
    position_m: tuple[float, float, float]
    quaternion_wxyz: tuple[float, float, float, float]
    wheel_angle_rad: tuple[float, float, float]


class MechanicalSimulatorProtocol(Protocol):
    def observe(self) -> dict[str, Any]: ...
    def set_state(self, state=None, tilt_deg=None, yaw_rate=0): ...


def native_rollout(config, case, controller, *, capture=True):
    from types import SimpleNamespace
    import mujoco
    import numpy as np
    from . import contact

    k = np.asarray(controller["K"], dtype=float)
    yaw = float(controller["yaw_rate_gain_nm_s"])
    if k.shape != (2, 6) or not np.isfinite(k).all() or not np.isfinite(yaw):
        raise ValueError("Invalid frozen numerical controller")
    regulator = SimpleNamespace(k=k, yaw_gain=yaw)
    poses = []
    if capture:
        # A subclass records the same observations as the unchanged evaluator.
        # A temporary module patch is protected because native calls can occur
        # concurrently from tool clients in a single process.
        from unittest.mock import patch
        with _CPU_CAPTURE_LOCK:
            original = contact.ContactPlant

            class RecordingPlant(original):
                def observe(self):
                    observed = super().observe()
                    poses.append({"time_s": float(self.data.time),
                                  "position_m": self.data.xpos[self.body].tolist(),
                                  "quaternion_wxyz": self.data.xquat[self.body].tolist(),
                                  "wheel_angle_rad": self.data.qpos[self.wheel_qpos].tolist()})
                    return observed

            with patch.object(contact, "ContactPlant", RecordingPlant):
                result = contact.simulate_contact(config, case, regulator)
        if len(poses) != len(result["rows"]):
            raise RuntimeError("Pose and telemetry sampling diverged")
        result["frames"] = [{**row, **pose} for row, pose in zip(result["rows"], poses)]
    else:
        with _CPU_CAPTURE_LOCK:
            result = contact.simulate_contact(config, case, regulator)
    result["metadata"] = {"backend": "native_mujoco_cpu", "accelerated": False,
                          "mujoco_version": mujoco.__version__, "precision": "float64",
                          "physics_timestep_s": config["physics"]["timestep_s"],
                          "control_period_s": config["physics"]["control_period_s"]}
    return result


def gpu_rollouts(configs, cases, controller):
    """A missing accelerator produces an explicit not-run result, never success."""
    try:
        from .multi_gpu import requested_gpu_ids, run_multi_gpu_batch
        gpu_ids = requested_gpu_ids()
        if gpu_ids:
            result = run_multi_gpu_batch(configs, cases, controller, gpu_ids)
        else:
            from .gpu_backend import run_batch
            result = run_batch(configs, cases, controller, require_gpu=True,
                               selected_indices=range(len(cases)))
    except (ImportError, RuntimeError) as error:
        return {"state": "not_run", "reason": str(error), "accelerated": False,
                "numeric_gpu_verified": False, "results": []}
    if result["metadata"].get("accelerated") is not True:
        raise RuntimeError("GPU backend returned non-accelerated execution")
    return {"state": "completed", "accelerated": True,
            "metadata": result["metadata"],
            "results": [{"summary": summary, "rows": result["selected_rows"][str(i)]}
                        for i, summary in enumerate(result["summaries"])]}


import threading
_CPU_CAPTURE_LOCK = threading.RLock()
