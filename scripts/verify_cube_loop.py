#!/usr/bin/env python3
"""Offline acceptance: Fake LLM proposals, real CPU physics, real SSOT feedback.

The fake only replaces proposal generation. It does not replace MuJoCo,
record persistence, context retrieval, the verifier, or the policy update.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from integrations.one_piece.mechanical_bridge import MechanicalBridge, atomic_json
from scenario.balancing_cube.loop import run_design_loop


class FakeDesigner:
    def __init__(self):
        self.prompts: list[dict] = []

    def generate(self, prompt: str) -> str:
        context = json.loads(prompt)
        self.prompts.append(context)
        mass = .05
        hypothesis = "Offline wiring test: compare a bounded ring mass change"
        parent = "reference"
        if len(self.prompts) > 1:
            feedback = context["feedback"][-1]
            measured = next(r for r in context["context_data"]["records"]
                            if r["kind"] == "simulation_run"
                            and r["data"].get("candidate_id") == feedback["candidate_id"])
            # Consume both persisted measurement and the evolved policy. This
            # deterministic fixture tests the feedback wiring, not LLM quality.
            direction = 1 if measured["data"]["score"] < 1 else -1
            mass += direction * min(.01, context["policy"]["suggested_search_step"] * .05)
            parent = feedback["candidate_id"]
            hypothesis = (f"Use stored {measured['id']}@{measured['revision']} score="
                          f"{measured['data']['score']} with policy revision "
                          f"{context['policy']['revision']} to test a bounded mass change")
        return json.dumps({
            "id": f"offline-fake-{len(self.prompts)}", "family": "dc_rs385",
            "parameters": {
                "side_m": .18, "print_mass_ref_kg": .12,
                "wheel_mass_kg": mass,
                "wheel_radius_ratio": .30, "inner_radius_ratio": .80,
                "wheel_thickness_m": .006,
            },
            "hypothesis": hypothesis, "parent_id": parent,
        })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bridge = MechanicalBridge(args.store)
    frozen = bridge.load_snapshot()
    fake = FakeDesigner()
    summary = run_design_loop(
        snapshot=frozen, output_dir=args.output, llm_client=fake,
        rounds=2, max_candidates=20, max_wall_s=1800,
        bridge=bridge, context_loader=bridge.load_snapshot,
    )
    second = fake.prompts[1] if len(fake.prompts) > 1 else {}
    reread = second.get("context_data", {}).get("records", [])
    first_candidate = summary.get("rounds", [{}])[0].get("feedback", {}).get("candidate_id")
    saved_feedback = [r for r in reread if r["kind"] == "simulation_run"
                      and r["data"].get("candidate_id") == first_candidate]
    results = [json.loads(p.read_text()) for p in sorted(args.output.glob("candidates/*/result.json"))]
    assertions = {
        "two_proposals": len(fake.prompts) == 2,
        "two_completed_rounds": summary["iterations_completed"] == 2,
        "measured_round_one_saved_and_reread": bool(saved_feedback),
        "round_two_reads_evolved_policy": second.get("policy", {}).get("revision") == 2,
        "policy_search_step_changed": bool(second) and second["policy"]["suggested_search_step"] != fake.prompts[0]["policy"]["suggested_search_step"],
        "round_two_receives_measured_feedback": bool(second.get("feedback")),
        "real_native_cpu_frames": bool(results) and all(
            r["records"] and all(row["backend"]["backend"] == "native_mujoco_cpu"
                                 and len(row["frames"]) > 1 for row in r["records"]) for r in results),
        "fixed_saved_controller": len({r["controller_digest"] for r in results}) == 1,
        "no_half_step_runs": all(r["half_step_adjudication_performed"] is False for r in results),
        "no_gpu_claim": all(r["numeric_gpu_verified"] is False for r in results),
        "no_physical_claim": summary["physical_verified"] is False,
        "outbox_acknowledged": bridge.outbox(args.output).flush()["pending"] == 0,
        "store_integrity": bridge.store.check(bridge.project_id)["ok"],
        "source_snapshot_unchanged": bridge.load_snapshot() == frozen,
    }
    result = {"passed": all(assertions.values()), "assertions": assertions,
              "run_id": summary["run_id"], "provider": "FakeDesigner; no real LLM calls",
              "execution": "native MuJoCo CPU; full frozen exploration matrix",
              "iterations": summary["iterations_completed"],
              "candidates": summary["candidates_evaluated"],
              "new_gpu_execution": False, "half_step_adjudication": False,
              "physical_validation": False,
              "source_snapshot_ref": frozen["source_snapshot_ref"]}
    atomic_json(args.output / "offline-acceptance.json", result)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
