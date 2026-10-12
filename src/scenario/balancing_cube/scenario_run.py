"""Normal EA job dispatch; all model/requirements/KDP inputs resolve from SSOT."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4


class BalancingCubeScenario:
    def run(self, output_dir=None, overrides=None, recreate_output=False,
            run_id=None, results_root=None, force=False, apply_proposals_path=None,
            design_history=None, on_step=None, on_phase=None, **kwargs):
        from integrations.one_piece.mechanical_bridge import MechanicalBridge
        from scenario.runner import load_scenario_config
        from scenario.jobs.resolve import default_results_root, sanitize_run_id
        from core.llm.factory import build_llm_client
        from .loop import run_design_loop
        config = load_scenario_config("balancing_cube", overrides)
        backend = {"cpu": "mujoco_cpu", "gpu": "mjx_gpu"}.get(config["backend"]["kind"], config["backend"]["kind"])
        if backend not in {"mujoco_cpu", "mjx_gpu"}:
            raise ValueError("balancing_cube backend must be mujoco_cpu or mjx_gpu")
        ssot = config["ssot"]
        if not ssot.get("path"):
            raise ValueError("balancing_cube requires ssot.path; model/requirements cannot be copied from local defaults")
        bridge = MechanicalBridge(ssot["path"], project_id=ssot["project_id"],
                                  snapshot_id=ssot["snapshot_id"], snapshot_revision=ssot["snapshot_revision"])
        snapshot = bridge.load_snapshot()
        run_id = sanitize_run_id(run_id or "cube-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
        root = Path(output_dir) if output_dir else (Path(results_root) if results_root else default_results_root()) / run_id
        mode = config["agents"]["mode"]
        if mode not in {"llm", "none"}:
            raise ValueError("balancing_cube supports llm or none; rule fallback is never labelled LLM")
        proposal = None
        if apply_proposals_path:
            document = json.loads(Path(apply_proposals_path).read_text())
            proposal = document.get("selected_candidate", document)
        llm = build_llm_client(config["agents"]["llm"]) if mode == "llm" else None
        iteration = config["iteration"]
        memory = None
        memory_config = config.get("memory", {})
        if memory_config.get("enabled"):
            from .memory import EngineeringMemory
            def memory():
                instance = EngineeringMemory(root / "memory" / "episodes.jsonl")
                for historical_run in memory_config.get("seed_runs", []):
                    instance.bootstrap_run(historical_run)
                return instance
        if on_phase:
            on_phase("fixed-dt EN/PI/R/E mechanical design loop")
        run_design_loop(snapshot=snapshot, output_dir=root, llm_client=llm,
            rounds=iteration["count"] if mode == "llm" and iteration["enabled"] else 1,
            max_candidates=iteration["max_candidates"], max_wall_s=iteration["max_wall_s"],
            stagnation_rounds=iteration["stagnation_rounds"], require_gpu=backend == "mjx_gpu",
            bridge=bridge, context_loader=bridge.load_snapshot, proposal=proposal,
            memory=memory, proposal_retries=iteration.get("proposal_retries", 0))
        return root


SCENARIO_REGISTRY = {"balancing_cube": BalancingCubeScenario()}
