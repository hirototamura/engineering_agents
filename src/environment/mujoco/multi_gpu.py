"""Opt-in persistent MJX workers with one isolated CUDA device per process.

``EA_MJX_GPU_IDS=0,1`` selects physical CUDA indices. Workers use spawn so a
parent JAX context is not forked. Each worker retains the unchanged run_batch
executable cache across candidates; ordered configuration/case pairs and the
saved controller pass through without changes.
"""
from __future__ import annotations

import atexit
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import os
import threading
import time


_POOLS = {}
_POOL_LOCK = threading.RLock()


def requested_gpu_ids():
    raw = os.environ.get("EA_MJX_GPU_IDS", "").strip()
    if not raw:
        return ()
    parts = tuple(part.strip() for part in raw.split(","))
    if any(not part.isascii() or not part.isdigit() for part in parts):
        raise ValueError("EA_MJX_GPU_IDS must contain comma-separated physical CUDA indices")
    ids = tuple(str(int(part)) for part in parts)
    if len(set(ids)) != len(ids):
        raise ValueError("EA_MJX_GPU_IDS cannot contain duplicate devices")
    return ids


def _initialize_worker(gpu_id):
    # No module in this worker imports JAX before this initializer. In
    # particular, backend and this module have no eager JAX dependency.
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu_id
    os.environ["JAX_PLATFORMS"] = "cuda"
    os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")


def _run_worker(configs, cases, controller):
    from .gpu_backend import run_batch
    result = run_batch(configs, cases, controller, require_gpu=True,
                       selected_indices=range(len(cases)))
    if result["metadata"].get("accelerated") is not True:
        raise RuntimeError("MJX worker did not execute on a GPU")
    result["metadata"]["physical_cuda_index"] = os.environ["CUDA_VISIBLE_DEVICES"]
    return result


def _pools(gpu_ids):
    with _POOL_LOCK:
        if gpu_ids not in _POOLS:
            context = multiprocessing.get_context("spawn")
            _POOLS[gpu_ids] = [ProcessPoolExecutor(max_workers=1, mp_context=context,
                initializer=_initialize_worker, initargs=(gpu_id,)) for gpu_id in gpu_ids]
        return _POOLS[gpu_ids]


def shutdown_workers():
    """Release only workers started by this module, including their GPU memory."""
    with _POOL_LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for group in pools:
        for executor in group:
            executor.shutdown(wait=True, cancel_futures=True)


atexit.register(shutdown_workers)


def run_multi_gpu_batch(configs, cases, controller, gpu_ids):
    if not configs or len(configs) != len(cases):
        raise ValueError("configs and cases must be nonempty paired lists")
    if not gpu_ids or len(set(gpu_ids)) != len(gpu_ids):
        raise ValueError("Explicit distinct GPU IDs are required")
    # Every explicitly requested device must execute a real case. Reject an
    # oversized request instead of silently skipping an unavailable device.
    if len(cases) < len(gpu_ids):
        raise ValueError("At least one simulation case per requested GPU is required")
    active_ids = tuple(gpu_ids)
    assignments = [list(range(worker, len(cases), len(active_ids)))
                   for worker in range(len(active_ids))]
    started = time.perf_counter()
    futures = [executor.submit(_run_worker, [configs[i] for i in indices],
                              [cases[i] for i in indices], controller)
               for executor, indices in zip(_pools(active_ids), assignments)]
    summaries, selected_rows, workers = [None] * len(cases), {}, []
    errors = []
    # Drain all futures even on failure: a partial batch cannot become success.
    for gpu_id, indices, future in zip(active_ids, assignments, futures):
        try:
            result = future.result()
            if (result["metadata"].get("accelerated") is not True
                    or len(result["summaries"]) != len(indices)
                    or set(result["selected_rows"]) != {str(i) for i in range(len(indices))}):
                raise RuntimeError("Incomplete or non-accelerated MJX shard")
            workers.append({**result["metadata"], "physical_cuda_index": gpu_id,
                            "global_case_indices": indices})
            for local_index, global_index in enumerate(indices):
                summaries[global_index] = result["summaries"][local_index]
                selected_rows[str(global_index)] = result["selected_rows"][str(local_index)]
        except Exception as error:
            errors.append(f"GPU {gpu_id}: {type(error).__name__}: {error}")
    if errors:
        raise RuntimeError("Requested multi-GPU batch failed; no GPU evidence accepted. " + "; ".join(errors))
    metadata = {
        "backend": "mujoco-mjx/jax-multi-gpu", "accelerated": True,
        "precision": "float32", "batch_size": len(cases),
        "requested_physical_cuda_indices": list(gpu_ids),
        "used_physical_cuda_indices": list(active_ids), "gpu_count": len(active_ids),
        "dispatch_wall_time_s": time.perf_counter() - started,
        "physics_timestep_s": configs[0]["physics"]["timestep_s"],
        "control_period_s": configs[0]["physics"]["control_period_s"],
        "controller_scope": "identical saved K and yaw gain in every worker",
        "workers": workers,
    }
    for field in ("jax_version", "mujoco_version", "mjx_version"):
        versions = {worker[field] for worker in workers}
        if len(versions) != 1:
            raise RuntimeError(f"MJX workers disagree on {field}")
        metadata[field] = versions.pop()
    return {"metadata": metadata, "summaries": summaries, "selected_rows": selected_rows}
