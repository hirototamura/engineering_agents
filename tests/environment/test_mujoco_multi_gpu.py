"""GPU orchestration contracts can be checked without a CUDA installation."""
from __future__ import annotations

import copy

import pytest

from environment.mujoco import multi_gpu


def _batch(count=12):
    configs = [{"physics": {"timestep_s": .0015, "control_period_s": .015}, "index": i}
               for i in range(count)]
    cases = [{"id": f"case-{i}", "seed": i} for i in range(count)]
    controller = {"K": [[1.0] * 6, [2.0] * 6], "yaw_rate_gain_nm_s": .03}
    return configs, cases, controller


class Future:
    def __init__(self, result=None, error=None):
        self.value, self.error = result, error

    def result(self):
        if self.error:
            raise self.error
        return self.value


class Executor:
    def __init__(self, gpu_id, calls, fail=False):
        self.gpu_id, self.calls, self.fail = gpu_id, calls, fail

    def submit(self, function, configs, cases, controller):
        self.calls.append((self.gpu_id, copy.deepcopy(configs), copy.deepcopy(cases), copy.deepcopy(controller)))
        if self.fail:
            return Future(error=RuntimeError("requested CUDA device unavailable"))
        return Future(result={
            "metadata": {"accelerated": True, "jax_version": "0.6.2", "mujoco_version": "3.3.7", "mjx_version": "3.3.7"},
            "summaries": [{"id": case["id"], "gpu": self.gpu_id} for case in cases],
            "selected_rows": {str(i): [{"id": case["id"], "seed": case["seed"]}] for i, case in enumerate(cases)},
        })


def test_requested_gpu_ids_reject_duplicates_and_invalid_devices(monkeypatch):
    monkeypatch.delenv("EA_MJX_GPU_IDS", raising=False)
    assert multi_gpu.requested_gpu_ids() == ()
    monkeypatch.setenv("EA_MJX_GPU_IDS", "0, 1,5")
    assert multi_gpu.requested_gpu_ids() == ("0", "1", "5")
    for invalid in ("0,00", "0,,1", "-1", "0,gpu", "０"):
        monkeypatch.setenv("EA_MJX_GPU_IDS", invalid)
        with pytest.raises(ValueError):
            multi_gpu.requested_gpu_ids()


def test_six_gpu_shards_preserve_order_cases_and_frozen_controller(monkeypatch):
    calls = []
    gpu_ids = tuple(map(str, range(6)))
    monkeypatch.setattr(multi_gpu, "_pools", lambda ids: [Executor(gpu, calls) for gpu in ids])
    configs, cases, controller = _batch()
    before = copy.deepcopy((configs, cases, controller))
    result = multi_gpu.run_multi_gpu_batch(configs, cases, controller, gpu_ids)
    assert (configs, cases, controller) == before
    assert [summary["id"] for summary in result["summaries"]] == [case["id"] for case in cases]
    assert [result["selected_rows"][str(i)][0]["seed"] for i in range(12)] == list(range(12))
    assert [len(call[1]) for call in calls] == [2] * 6
    assert [row["global_case_indices"] for row in result["metadata"]["workers"]] == [[i, i + 6] for i in range(6)]
    assert all(call[3] == controller for call in calls)
    assert result["metadata"]["used_physical_cuda_indices"] == list(gpu_ids)
    assert result["metadata"]["gpu_count"] == 6


def test_one_missing_gpu_rejects_the_entire_batch(monkeypatch):
    calls = []
    monkeypatch.setattr(multi_gpu, "_pools", lambda ids: [Executor(gpu, calls, fail=gpu == "1") for gpu in ids])
    with pytest.raises(RuntimeError, match="GPU 1: RuntimeError: requested CUDA device unavailable"):
        multi_gpu.run_multi_gpu_batch(*_batch(), ("0", "1", "2"))
    assert len(calls) == 3


def test_worker_binding_precedes_jax_import_and_disables_preallocation_by_default(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "original")
    monkeypatch.setenv("JAX_PLATFORMS", "original")
    monkeypatch.delenv("XLA_PYTHON_CLIENT_PREALLOCATE", raising=False)
    multi_gpu._initialize_worker("5")
    assert multi_gpu.os.environ["CUDA_VISIBLE_DEVICES"] == "5"
    assert multi_gpu.os.environ["JAX_PLATFORMS"] == "cuda"
    assert multi_gpu.os.environ["XLA_PYTHON_CLIENT_PREALLOCATE"] == "false"


def test_gpu_failure_is_not_reported_as_completed_or_cpu_fallback(monkeypatch):
    from environment.mujoco.backend import gpu_rollouts
    monkeypatch.setenv("EA_MJX_GPU_IDS", "0,1")
    def missing(*args):
        raise RuntimeError("GPU 1 unavailable")
    monkeypatch.setattr(multi_gpu, "run_multi_gpu_batch", missing)
    result = gpu_rollouts(*_batch())
    assert result["state"] == "not_run"
    assert result["accelerated"] is False
    assert result["numeric_gpu_verified"] is False
    assert result["results"] == []


def test_too_many_requested_devices_cannot_silently_skip_a_missing_gpu():
    with pytest.raises(ValueError, match="one simulation case per requested GPU"):
        multi_gpu.run_multi_gpu_batch(*_batch(1), ("0", "99"))


def test_worker_pools_persist_and_use_spawn(monkeypatch):
    calls, executors = [], []
    monkeypatch.setattr(multi_gpu, "_POOLS", {})
    def executor(**kwargs):
        calls.append(kwargs)
        value = object()
        executors.append(value)
        return value
    monkeypatch.setattr(multi_gpu, "ProcessPoolExecutor", executor)
    first = multi_gpu._pools(("0", "1"))
    assert multi_gpu._pools(("0", "1")) is first
    assert len(calls) == 2
    assert all(call["mp_context"].get_start_method() == "spawn" for call in calls)
    assert [call["initargs"] for call in calls] == [("0",), ("1",)]
