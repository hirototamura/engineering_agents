"""A design problem adapter separates proposing, compilation and verification."""
from __future__ import annotations

import copy
from pathlib import Path
import time
from typing import Protocol

from .design import compile_controller, compile_mechanical, digest, trial_matrix
from .evaluation import aggregate, paired_metrics, screening


class DesignProblemAdapter(Protocol):
    def reset(self): ...
    def compile(self, proposal): ...
    def rollout(self, compiled, *, stage="exploration", require_gpu=False, deadline=None): ...
    def feedback(self, result): ...


class RolloutDeadlineExceeded(TimeoutError):
    def __init__(self, *, compiled, stage, cpu, total, phase):
        super().__init__("wall_budget_during_" + phase)
        self.evidence = {"state": "incomplete", "reason": str(self), "candidate_id": compiled["id"],
                         "input_digest": compiled["input_digest"], "compiled": copy.deepcopy(compiled), "stage": stage,
                         "completed_cpu_trials": len(cpu), "expected_trials": total,
                         "partial_cpu_results": cpu, "numeric_gpu_verified": False,
                         "physical_verified": False, "half_step_adjudication_performed": False}


class RolloutExecutionFailed(RuntimeError):
    def __init__(self, *, compiled, stage, cpu, total, error):
        super().__init__(f"{type(error).__name__}: {error}")
        self.evidence = {"state": "failed", "reason": str(self), "candidate_id": compiled["id"],
                         "compiled": copy.deepcopy(compiled), "input_digest": compiled["input_digest"],
                         "stage": stage, "partial_cpu_results": cpu, "completed_cpu_trials": len(cpu),
                         "expected_trials": total, "numeric_cpu_verified": False,
                         "numeric_gpu_verified": False, "physical_verified": False,
                         "half_step_adjudication_performed": False}


class BalancingCubeAdapter:
    def __init__(self, snapshot):
        self.snapshot = copy.deepcopy(snapshot)
        for required in ("mission", "requirements", "kdps", "model", "controller", "contract", "plan", "families"):
            if required not in self.snapshot:
                raise ValueError(f"SSOT snapshot missing {required}")
        self.frozen_digest = digest(self.snapshot)
        self.code_digests = self._code_digests()

    @staticmethod
    def _code_digests():
        import hashlib
        from environment import mujoco as physics
        root = Path(physics.__file__).parent
        files = [root / name for name in ("model.py", "control.py", "contact.py", "gpu_backend.py", "backend.py")]
        files += [Path(__file__), Path(__file__).with_name("design.py"), Path(__file__).with_name("evaluation.py")]
        return {str(path.name): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}

    def reset(self):
        if digest(self.snapshot) != self.frozen_digest or self._code_digests() != self.code_digests:
            raise ValueError("invalid_contract_tamper: frozen reset/verifier/constraints changed")
        return {"stage": "EN", "snapshot_digest": self.frozen_digest,
                "code_digests": self.code_digests,
                "timestep_s": self.snapshot["model"]["physics"]["timestep_s"],
                "holdout_status": "public_integrity_checked", "physical_verified": False}

    def compile(self, proposal):
        self.reset()
        config = compile_mechanical(proposal, self.snapshot)
        controller = compile_controller(proposal, self.snapshot)
        return {"id": proposal["id"], "proposal": copy.deepcopy(proposal), "config": config,
                "controller": controller,
                "input_digest": digest({"config": config, "controller": controller,
                                        "snapshot_digest": self.frozen_digest}),
                "campaign_id": "controller-" + digest(controller)[:16]}

    def rollout(self, compiled, *, stage="exploration", require_gpu=False, deadline=None):
        from environment.mujoco.backend import native_rollout, gpu_rollouts
        self.reset()
        input_digest = digest({"config": compiled["config"], "controller": compiled["controller"],
                               "snapshot_digest": self.frozen_digest})
        if input_digest != compiled["input_digest"]:
            raise ValueError("Candidate changed after compilation")
        trials = trial_matrix(compiled["config"], self.snapshot, compiled["id"], stage)
        cpu = []
        def check_deadline(phase):
            if deadline is not None and time.monotonic() >= deadline:
                raise RolloutDeadlineExceeded(compiled=compiled, stage=stage, cpu=cpu, total=len(trials), phase=phase)
        for trial in trials:
            check_deadline("cpu_case_boundary")
            try:
                cpu.append(native_rollout(trial["config"], trial["case"], compiled["controller"]))
            except Exception as error:
                raise RolloutExecutionFailed(compiled=compiled, stage=stage, cpu=cpu, total=len(trials), error=error) from error
        check_deadline("gpu_batch_boundary")
        try:
            gpu = gpu_rollouts([t["config"] for t in trials], [t["case"] for t in trials], compiled["controller"]) if require_gpu else {
                "state": "not_run", "reason": "GPU execution was not requested", "accelerated": False, "results": []}
        except Exception as error:
            raise RolloutExecutionFailed(compiled=compiled, stage=stage, cpu=cpu, total=len(trials), error=error) from error
        check_deadline("gpu_batch_completion")
        records = []
        for i, (trial, native) in enumerate(zip(trials, cpu)):
            record = {"run_id": trial["case"]["id"], "domain_id": trial["key"][0],
                      "condition_id": trial["key"][1], "seed": trial["key"][2],
                      "summary": native["summary"], "rows": native["rows"], "frames": native["frames"],
                      "backend": native["metadata"], "evaluation_summary_source": "native_cpu_reference",
                      "screening": screening(native["summary"], self.snapshot["contract"]),
                      "physics_timestep_s": trial["config"]["physics"]["timestep_s"],
                      "gpu_state": gpu["state"], "physical_verified": False}
            if gpu["state"] == "completed":
                record["gpu_summary"] = gpu["results"][i]["summary"]
                record["paired_metrics"] = paired_metrics(native, gpu["results"][i], self.snapshot["contract"],
                    control_period_s=trial["config"]["physics"]["control_period_s"])
                record["gpu_backend"] = gpu["metadata"]
            else:
                record["paired_metrics"] = {"passed": False, "state": "not_run", "reason": gpu.get("reason")}
            records.append(record)
        self.reset()
        result = aggregate(records, self.snapshot, [t["key"] for t in trials])
        return {**result, "candidate_id": compiled["id"], "input_digest": input_digest,
                "campaign_id": compiled["campaign_id"], "controller_digest": digest(compiled["controller"]),
                "snapshot_digest": self.frozen_digest, "stage": stage,
                "gpu_state": gpu["state"], "agreement_state": "verified" if result["numeric_gpu_verified"] else "inconclusive",
                "half_step_adjudication_performed": False}

    def feedback(self, result):
        # PI receives measured summaries and failures; it is never asked to mark
        # its own design as passed or to rewrite verification requirements.
        return {"candidate_id": result["candidate_id"], "score": result["score"],
                "all_screening_passed": result["all_screening_passed"],
                "numeric_gpu_verified": result["numeric_gpu_verified"],
                "failure_metrics": sorted({c["metric"] for r in result["records"] for c in r["screening"] if not c["passed"]}),
                "physical_verified": False}
