import csv
import json
import argparse
from collections import Counter
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument(
    "--root",
    default="runs/phase3-rescored",
    help="Chain run root containing chain_summary.json and iteration directories.",
)
parser.add_argument("--prefix", default="phase3", help="Output filename prefix.")
args = parser.parse_args()

ROOT = Path(args.root)
PREFIX = args.prefix
OUT = Path("outputs")
OUT.mkdir(exist_ok=True)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def get_path(obj, parts, default=None):
    cur = obj
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def fields_from_proposal(path):
    if not path.exists():
        return {}
    data = load_json(path)
    for change in data.get("changes", []):
        if change.get("change_kind") == "capacity_profile":
            return change.get("payload", {}).get("fields", {}) or {}
    return {}


def config_capacity(path):
    vals = {}
    section = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        key_val = line.strip()
        if ":" not in key_val:
            continue
        key, val = key_val.split(":", 1)
        level = indent // 2
        section = section[:level]
        section.append(key.strip())
        full = ".".join(section)
        val = val.strip()
        if full in {
            "plant_sim.ars.capacity_kg_day",
            "plant_sim.ogs.max_o2_kg_day",
            "plant_sim.wrs.max_feed_l_per_operation",
        }:
            vals[full] = float(val)
    return vals


def trace_metrics(path):
    tools = Counter()
    required = None
    collected = None
    missing = None
    candidates_run = None
    theoretical = {}
    ran_candidate_results = []
    parse_notes = []
    if not path.exists():
        return {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event") == "tool_call":
            tool = event.get("tool")
            tools[tool] += 1
            evidence = event.get("evidence") or {}
            required = evidence.get("required", required)
            collected = evidence.get("collected", collected)
            missing = evidence.get("missing", missing)
            candidates_run = evidence.get("candidates_run", candidates_run)
            result = event.get("result") or {}
            if tool == "compute_theoretical_capacity":
                subs = result.get("subsystems", {})
                theoretical = {
                    "theory_ars_required_nameplate": get_path(subs, ["ars", "required_nameplate_kg_day"]),
                    "theory_ars_coverage": get_path(subs, ["ars", "coverage_ratio"]),
                    "theory_ogs_required_nameplate": get_path(subs, ["ogs", "required_nameplate_kg_day"]),
                    "theory_ogs_coverage": get_path(subs, ["ogs", "coverage_ratio"]),
                    "theory_wrs_coverage": get_path(subs, ["wrs", "coverage_ratio"]),
                    "theory_wrs_request_limited": get_path(subs, ["wrs", "request_limited"]),
                }
            elif tool == "run_design_candidate":
                outcome = result.get("outcome") or result
                ran_candidate_results.append(
                    {
                        "candidate_crew_remaining": outcome.get("crew_remaining"),
                        "candidate_score": outcome.get("evaluation_score"),
                        "candidate_peak_co2": outcome.get("peak_co2_storage_kg"),
                        "candidate_min_o2": outcome.get("min_o2_storage_kg"),
                    }
                )
        elif event.get("event") in {"decision_parsed", "decision_parse_failed"}:
            if event.get("note"):
                parse_notes.append(event.get("note"))
    out = {
        "tool_call_count": sum(tools.values()),
        "tool_counts": dict(tools),
        "required_evidence_count": len(required or []),
        "collected_evidence_count": len(collected or []),
        "missing_evidence_count": len(missing or []),
        "trace_candidates_run": candidates_run,
        "parse_note_count": len(parse_notes),
    }
    out.update(theoretical)
    if ran_candidate_results:
        out.update(ran_candidate_results[-1])
    return out


def flatten_axes(evaluation_compact):
    axes = (evaluation_compact or {}).get("axes", {})
    return {
        f"axis_{name}": val.get("score")
        for name, val in axes.items()
        if isinstance(val, dict)
    }


rows = []
chain = load_json(ROOT / "chain_summary.json")
for run in chain.get("runs", []):
    i = run["iteration"]
    idir = ROOT / f"{i:02d}"
    summary = load_json(idir / "summary.json")
    proposal = load_json(idir / "design_proposals.json")
    fields = fields_from_proposal(idir / "design_proposals.json")
    cfg_fields = config_capacity(idir / "scenario_config.yaml")
    expected = proposal.get("expected_outcome") or {}
    constraints = proposal.get("constraint_evaluation") or {}
    trace = trace_metrics(idir / "tool_trace.jsonl")
    compact = summary.get("evaluation_compact") or {}
    row = {
        "iteration": i,
        "apply_proposals_path": run.get("apply_proposals_path"),
        "crew_remaining": summary.get("crew_remaining"),
        "crew_lost": summary.get("crew_lost"),
        "score": summary.get("evaluation_score"),
        "physics_gate_passed": summary.get("physics_gate_passed"),
        "peak_co2": summary.get("peak_co2_storage_kg"),
        "min_o2": summary.get("min_o2_storage_kg"),
        "final_water": summary.get("final_product_water_reserve_l"),
        "final_status": proposal.get("final_status"),
        "decision_source": proposal.get("decision_source"),
        "selected_candidate_id": proposal.get("selected_candidate_id"),
        "config_ars": cfg_fields.get("plant_sim.ars.capacity_kg_day"),
        "config_ogs": cfg_fields.get("plant_sim.ogs.max_o2_kg_day"),
        "config_wrs": cfg_fields.get("plant_sim.wrs.max_feed_l_per_operation"),
        "proposal_ars": fields.get("plant_sim.ars.capacity_kg_day"),
        "proposal_ogs": fields.get("plant_sim.ogs.max_o2_kg_day"),
        "proposal_wrs": fields.get("plant_sim.wrs.max_feed_l_per_operation"),
        "expected_crew_remaining": expected.get("crew_remaining"),
        "expected_score": expected.get("evaluation_score"),
        "expected_peak_co2": expected.get("peak_co2_storage_kg"),
        "expected_min_o2": expected.get("min_o2_storage_kg"),
        "constraint_status": constraints.get("constraint_status"),
        "total_mass_kg": constraints.get("total_mass_kg"),
        "total_cost_musd": constraints.get("total_cost_musd"),
        "total_volume_m3": constraints.get("total_volume_m3"),
        "design_penalty": constraints.get("design_penalty"),
        "llm_turn_count": proposal.get("llm_turn_count"),
        "evidence_missing_in_proposal": len((proposal.get("evidence") or {}).get("missing") or []),
    }
    row.update(flatten_axes(compact))
    row.update(trace)
    rows.append(row)

fieldnames = sorted({key for row in rows for key in row})
with (OUT / f"{PREFIX}_iteration_metrics.csv").open("w", encoding="utf-8", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

summary_rows = [
    ["iterations_requested", chain.get("iterations_requested")],
    ["iterations_completed", chain.get("iterations_completed")],
    ["crew_remaining_first", chain.get("crew_remaining_first")],
    ["crew_remaining_last", chain.get("crew_remaining_last")],
    ["crew_remaining_baseline_replay", chain.get("crew_remaining_baseline_replay")],
    ["crew_remaining_final_replay", chain.get("crew_remaining_final_replay")],
    ["verdict", chain.get("verdict")],
    ["final_answer_status", get_path(chain, ["final_answer", "status"])],
    ["final_answer_selected_candidate_id", get_path(chain, ["final_answer", "selected_candidate_id"])],
    ["final_answer_iteration", get_path(chain, ["final_answer", "iteration"])],
]
with (OUT / f"{PREFIX}_chain_key_summary.csv").open("w", encoding="utf-8", newline="") as fh:
    writer = csv.writer(fh)
    writer.writerow(["metric", "value"])
    writer.writerows(summary_rows)

iters = [r["iteration"] for r in rows]
crew = [r["crew_remaining"] for r in rows]
score = [r["score"] for r in rows]


def scale(v, lo, hi, a, b):
    if hi == lo:
        return (a + b) / 2
    return a + (v - lo) * (b - a) / (hi - lo)


def polyline(points, color, width=2):
    return (
        f'<polyline fill="none" stroke="{color}" stroke-width="{width}" '
        f'points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in points)}" />'
    )


def circle(x, y, color, r=3):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" />'


def write_dual_axis_svg(path, title):
    w, h = 1200, 620
    left, right, top, bottom = 80, 80, 60, 70
    x0, x1 = left, w - right
    y0, y1 = h - bottom, top
    xmin, xmax = min(iters), max(iters)
    crew_pts = [
        (scale(i, xmin, xmax, x0, x1), scale(v, 0, 50, y0, y1))
        for i, v in zip(iters, crew)
    ]
    score_pts = [
        (scale(i, xmin, xmax, x0, x1), scale(v, 0, 100, y0, y1))
        for i, v in zip(iters, score)
    ]
    elems = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{w/2}" y="32" font-size="22" text-anchor="middle" font-family="Arial">{title}</text>',
        f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="#333"/>',
        f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}" stroke="#333"/>',
        f'<line x1="{x1}" y1="{y0}" x2="{x1}" y2="{y1}" stroke="#333"/>',
    ]
    for tick in range(0, 51, 10):
        y = scale(tick, 0, 50, y0, y1)
        elems.append(f'<line x1="{x0-5}" y1="{y:.1f}" x2="{x0}" y2="{y:.1f}" stroke="#333"/>')
        elems.append(f'<text x="{x0-10}" y="{y+5:.1f}" font-size="13" text-anchor="end" font-family="Arial" fill="#0b6e4f">{tick}</text>')
    for tick in range(0, 101, 20):
        y = scale(tick, 0, 100, y0, y1)
        elems.append(f'<line x1="{x1}" y1="{y:.1f}" x2="{x1+5}" y2="{y:.1f}" stroke="#333"/>')
        elems.append(f'<text x="{x1+10}" y="{y+5:.1f}" font-size="13" font-family="Arial" fill="#a23e2a">{tick}</text>')
    tick_step = 1 if xmax <= 15 else 5
    for tick in range(xmin, xmax + 1, tick_step):
        x = scale(tick, xmin, xmax, x0, x1)
        elems.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y0+5}" stroke="#333"/>')
        elems.append(f'<text x="{x:.1f}" y="{y0+24}" font-size="12" text-anchor="middle" font-family="Arial">{tick}</text>')
    for tick in range(0, 51, 10):
        y = scale(tick, 0, 50, y0, y1)
        elems.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#e6e6e6"/>')
    elems.append(polyline(crew_pts, "#0b6e4f", 3))
    elems.append(polyline(score_pts, "#a23e2a", 2))
    elems.extend(circle(x, y, "#0b6e4f", 3) for x, y in crew_pts)
    elems.extend(circle(x, y, "#a23e2a", 2.5) for x, y in score_pts)
    elems.append(f'<text x="{w/2}" y="{h-18}" font-size="15" text-anchor="middle" font-family="Arial">Iteration</text>')
    elems.append(f'<text x="22" y="{h/2}" font-size="15" text-anchor="middle" transform="rotate(-90,22,{h/2})" font-family="Arial" fill="#0b6e4f">Crew remaining / 50</text>')
    elems.append(f'<text x="{w-22}" y="{h/2}" font-size="15" text-anchor="middle" transform="rotate(90,{w-22},{h/2})" font-family="Arial" fill="#a23e2a">Evaluation score / 100</text>')
    elems.append('<rect x="865" y="84" width="245" height="58" fill="white" stroke="#ccc"/>')
    elems.append('<line x1="880" y1="105" x2="925" y2="105" stroke="#0b6e4f" stroke-width="3"/><text x="935" y="110" font-size="14" font-family="Arial">Crew remaining</text>')
    elems.append('<line x1="880" y1="128" x2="925" y2="128" stroke="#a23e2a" stroke-width="2"/><text x="935" y="133" font-size="14" font-family="Arial">Evaluation score</text>')
    elems.append("</svg>")
    path.write_text("\n".join(elems), encoding="utf-8")


def write_variables_svg(path, title):
    w, h = 1200, 620
    left, right, top, bottom = 80, 40, 60, 70
    x0, x1 = left, w - right
    y0, y1 = h - bottom, top
    series = [
        ("ARS kg/day", [r["config_ars"] for r in rows], "#245c9e"),
        ("OGS kg/day", [r["config_ogs"] for r in rows], "#a23e2a"),
        ("WRS L/op", [r["config_wrs"] for r in rows], "#0b6e4f"),
    ]
    lo, hi = 0, 80
    elems = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{w/2}" y="32" font-size="22" text-anchor="middle" font-family="Arial">{title}</text>',
        f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="#333"/>',
        f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}" stroke="#333"/>',
    ]
    for tick in range(0, 81, 10):
        y = scale(tick, lo, hi, y0, y1)
        elems.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#e6e6e6"/>')
        elems.append(f'<text x="{x0-10}" y="{y+5:.1f}" font-size="13" text-anchor="end" font-family="Arial">{tick}</text>')
    xmin, xmax = min(iters), max(iters)
    tick_step = 1 if xmax <= 15 else 5
    for tick in range(xmin, xmax + 1, tick_step):
        x = scale(tick, xmin, xmax, x0, x1)
        elems.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y0+5}" stroke="#333"/>')
        elems.append(f'<text x="{x:.1f}" y="{y0+24}" font-size="12" text-anchor="middle" font-family="Arial">{tick}</text>')
    for val, label, dash in [(20.8, "ARS theory floor 20.8", "6 5"), (42.0, "OGS theory floor 42.0", "2 5")]:
        y = scale(val, lo, hi, y0, y1)
        elems.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#777" stroke-dasharray="{dash}"/>')
        elems.append(f'<text x="{x1-6}" y="{y-5:.1f}" font-size="12" text-anchor="end" font-family="Arial" fill="#555">{label}</text>')
    for label, values, color in series:
        pts = [(scale(i, xmin, xmax, x0, x1), scale(v, lo, hi, y0, y1)) for i, v in zip(iters, values)]
        elems.append(polyline(pts, color, 2.5))
        elems.extend(circle(x, y, color, 3) for x, y in pts)
    elems.append(f'<text x="{w/2}" y="{h-18}" font-size="15" text-anchor="middle" font-family="Arial">Iteration</text>')
    elems.append(f'<text x="22" y="{h/2}" font-size="15" text-anchor="middle" transform="rotate(-90,22,{h/2})" font-family="Arial">Proposed capacity</text>')
    elems.append('<rect x="895" y="84" width="240" height="82" fill="white" stroke="#ccc"/>')
    yleg = 106
    for label, values, color in series:
        elems.append(f'<line x1="910" y1="{yleg}" x2="955" y2="{yleg}" stroke="{color}" stroke-width="3"/><text x="965" y="{yleg+5}" font-size="14" font-family="Arial">{label}</text>')
        yleg += 23
    elems.append("</svg>")
    path.write_text("\n".join(elems), encoding="utf-8")


def write_space_svg(path, title):
    w, h = 900, 680
    left, right, top, bottom = 80, 50, 60, 70
    x0, x1 = left, w - right
    y0, y1 = h - bottom, top
    xs = [r["config_ars"] for r in rows]
    ys = [r["config_ogs"] for r in rows]
    xlo, xhi = min(xs) - 1, max(xs) + 1
    ylo, yhi = min(ys) - 2, max(ys) + 2
    elems = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{w/2}" y="32" font-size="22" text-anchor="middle" font-family="Arial">{title}</text>',
        f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="#333"/>',
        f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}" stroke="#333"/>',
    ]
    for r in rows:
        x = scale(r["config_ars"], xlo, xhi, x0, x1)
        y = scale(r["config_ogs"], ylo, yhi, y0, y1)
        green = int(scale(r["crew_remaining"], 0, 50, 90, 185))
        red = int(scale(r["crew_remaining"], 0, 50, 180, 20))
        color = f"rgb({red},{green},120)"
        elems.append(circle(x, y, color, 6))
        if r["crew_remaining"] == 50 or r["iteration"] in {1, 23, 50}:
            elems.append(f'<text x="{x+8:.1f}" y="{y-8:.1f}" font-size="12" font-family="Arial">{r["iteration"]}</text>')
    elems.append(f'<text x="{w/2}" y="{h-18}" font-size="15" text-anchor="middle" font-family="Arial">ARS capacity kg/day</text>')
    elems.append(f'<text x="22" y="{h/2}" font-size="15" text-anchor="middle" transform="rotate(-90,22,{h/2})" font-family="Arial">OGS capacity kg/day</text>')
    for tick in range(int(xlo // 5 * 5), int(xhi) + 5, 5):
        x = scale(tick, xlo, xhi, x0, x1)
        elems.append(f'<text x="{x:.1f}" y="{y0+24}" font-size="12" text-anchor="middle" font-family="Arial">{tick}</text>')
    for tick in range(int(ylo // 5 * 5), int(yhi) + 5, 5):
        y = scale(tick, ylo, yhi, y0, y1)
        elems.append(f'<text x="{x0-10}" y="{y+5:.1f}" font-size="12" text-anchor="end" font-family="Arial">{tick}</text>')
    elems.append("</svg>")
    path.write_text("\n".join(elems), encoding="utf-8")


write_dual_axis_svg(OUT / f"{PREFIX}_survival_score_trend.svg", f"SSOS ECLSS design chain: survival and score over {len(rows)} iterations")
write_variables_svg(OUT / f"{PREFIX}_design_variables_trend.svg", f"Effective design variables over {len(rows)} iterations")
write_space_svg(OUT / f"{PREFIX}_design_space_survival.svg", "Design space visited; color indicates crew remaining")

best_score = max(rows, key=lambda r: r["score"])
full_survival = [r for r in rows if r["crew_remaining"] == 50]
findings_path = OUT / f"{PREFIX}_iteration_findings.json"
with findings_path.open("w", encoding="utf-8") as fh:
    json.dump(
        {
            "chain_summary": dict(summary_rows),
            "score_min": min(score),
            "score_max": max(score),
            "score_mean": sum(score) / len(score),
            "crew_remaining_counts": dict(Counter(crew)),
            "full_survival_iterations": [r["iteration"] for r in full_survival],
            "best_score_iteration": best_score["iteration"],
            "best_score": best_score["score"],
            "best_score_crew_remaining": best_score["crew_remaining"],
            "final_iteration": rows[-1],
        },
        fh,
        ensure_ascii=False,
        indent=2,
    )

print(json.dumps(load_json(findings_path), ensure_ascii=False, indent=2))
