import csv
import json
from collections import Counter
from pathlib import Path


OUT = Path("outputs")
RUNS = {
    "initial": {
        "prefix": "phase1",
        "root": Path("runs/phase1-no-chain-memory"),
        "label": "Initial PR65",
    },
    "memory_db": {
        "prefix": "phase2",
        "root": Path("runs/phase2-chain-memory"),
        "label": "Memory enabled",
    },
    "eval_improve": {
        "prefix": "phase3",
        "root": Path("runs/phase3-rescored"),
        "label": "Memory + scoring sensitivity",
    },
}


def read_rows(prefix):
    with (OUT / f"{prefix}_iteration_metrics.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def as_float(row, key):
    value = row.get(key, "")
    return None if value in {"", None} else float(value)


def as_int(row, key):
    value = row.get(key, "")
    return None if value in {"", None} else int(float(value))


def memory_presence(root):
    present = []
    absent = []
    for idir in sorted([p for p in root.iterdir() if p.is_dir() and p.name.isdigit()]):
        trace = idir / "tool_trace.jsonl"
        if not trace.exists():
            absent.append(int(idir.name))
            continue
        found_load = False
        found_memory = False
        for line in trace.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("event") != "tool_call" or event.get("tool") != "load_run_artifacts":
                continue
            found_load = True
            result = event.get("result") or {}
            if result.get("chain_memory_compact"):
                found_memory = True
        if found_memory:
            present.append(int(idir.name))
        elif found_load:
            absent.append(int(idir.name))
    memory_file = root / "compact_chain_memory.json"
    return {
        "present_iterations": present,
        "absent_iterations": absent,
        "file_exists": memory_file.exists(),
        "file_size_bytes": memory_file.stat().st_size if memory_file.exists() else 0,
    }


def summarize(prefix, root, label):
    rows = read_rows(prefix)
    chain = json.loads((root / "chain_summary.json").read_text(encoding="utf-8"))
    scores = [as_float(row, "score") for row in rows]
    crew = [as_int(row, "crew_remaining") for row in rows]
    best = max(rows, key=lambda row: as_float(row, "score") or -1)
    final = rows[-1]
    complete_proposals = [
        row
        for row in rows
        if all(as_float(row, key) is not None for key in ["proposal_ars", "proposal_ogs", "proposal_wrs"])
    ]
    incomplete = [int(row["iteration"]) for row in rows if row not in complete_proposals]
    config_drop_transitions = []
    for prev, cur in zip(rows, rows[1:]):
        dropped = []
        for key in ["config_ars", "config_ogs", "config_wrs"]:
            p = as_float(prev, key)
            c = as_float(cur, key)
            if p is not None and c is not None and c < p - 1e-9:
                dropped.append(key.replace("config_", "").upper())
        if dropped:
            config_drop_transitions.append(
                {
                    "from": int(prev["iteration"]),
                    "to": int(cur["iteration"]),
                    "fields": dropped,
                    "prev": {k: as_float(prev, k) for k in ["config_ars", "config_ogs", "config_wrs"]},
                    "cur": {k: as_float(cur, k) for k in ["config_ars", "config_ogs", "config_wrs"]},
                }
            )
    unique_configs = Counter(
        (
            round(as_float(row, "config_ars") or 0, 6),
            round(as_float(row, "config_ogs") or 0, 6),
            round(as_float(row, "config_wrs") or 0, 6),
        )
        for row in rows
    )
    best_components = {
        "survival": as_float(best, "axis_actor_survival"),
        "tcl": as_float(best, "axis_tcl"),
        "environment": as_float(best, "axis_environment_trajectory"),
        "recovery": as_float(best, "axis_resource_recovery"),
        "cost": as_float(best, "axis_cost"),
        "mass": as_float(best, "axis_mass"),
        "ops_physics": (as_float(best, "axis_actor_decision") or 0)
        + (as_float(best, "axis_physical_response") or 0),
    }
    final_components = {
        "survival": as_float(final, "axis_actor_survival"),
        "tcl": as_float(final, "axis_tcl"),
        "environment": as_float(final, "axis_environment_trajectory"),
        "recovery": as_float(final, "axis_resource_recovery"),
        "cost": as_float(final, "axis_cost"),
        "mass": as_float(final, "axis_mass"),
        "ops_physics": (as_float(final, "axis_actor_decision") or 0)
        + (as_float(final, "axis_physical_response") or 0),
    }
    return {
        "label": label,
        "prefix": prefix,
        "iterations_requested": chain.get("iterations_requested"),
        "iterations_completed": chain.get("iterations_completed"),
        "baseline_replay_survivors": chain.get("crew_remaining_baseline_replay"),
        "final_replay_survivors": chain.get("crew_remaining_final_replay"),
        "verdict": chain.get("verdict"),
        "final_answer_iteration": ((chain.get("final_answer") or {}).get("iteration")),
        "first_survivors": crew[0],
        "final_survivors": crew[-1],
        "full_survival_count": sum(1 for val in crew if val == 50),
        "zero_survival_count": sum(1 for val in crew if val == 0),
        "score_min": min(scores),
        "score_max": max(scores),
        "score_mean": sum(scores) / len(scores),
        "best_iteration": int(best["iteration"]),
        "best_score": as_float(best, "score"),
        "best_survivors": as_int(best, "crew_remaining"),
        "best_config": {
            "ars": as_float(best, "config_ars"),
            "ogs": as_float(best, "config_ogs"),
            "wrs": as_float(best, "config_wrs"),
        },
        "best_components": best_components,
        "final_iteration": int(final["iteration"]),
        "final_score": as_float(final, "score"),
        "final_config": {
            "ars": as_float(final, "config_ars"),
            "ogs": as_float(final, "config_ogs"),
            "wrs": as_float(final, "config_wrs"),
        },
        "final_components": final_components,
        "complete_proposal_count": len(complete_proposals),
        "incomplete_proposal_iterations": incomplete,
        "config_drop_transition_count": len(config_drop_transitions),
        "config_drop_transitions": config_drop_transitions[:20],
        "unique_config_count": len(unique_configs),
        "most_common_configs": [
            {"ars": cfg[0], "ogs": cfg[1], "wrs": cfg[2], "count": count}
            for cfg, count in unique_configs.most_common(5)
        ],
        "memory": memory_presence(root),
    }


summary = {
    key: summarize(spec["prefix"], spec["root"], spec["label"])
    for key, spec in RUNS.items()
}

(OUT / "ssos_three_way_comparison_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(summary, ensure_ascii=False, indent=2))
