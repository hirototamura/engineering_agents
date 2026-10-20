"""Build the research article from a frozen, inspectable evidence extract.

No simulation, LLM call, or canonical-store mutation occurs here. Use --refresh
to extract original local artifacts again; the packaged extract supports offline
rebuilding without the large campaign archives.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import quote

HERE = Path(__file__).parent
RUNS = ("qwen27b-memory10-20261012-r2", "qwen27b-memory20-20261012")
MODEL_REVISION = "reviewed-20261019-1"
REPLAY_FIELDS = (
    "time_s", "position_m", "quaternion_wxyz", "wheel_angle_rad", "tilt_total_deg",
    "wheel_x_rpm", "wheel_y_rpm", "wheel_z_rpm", "motor_x_nm", "motor_y_nm", "motor_z_nm",
    "speed_governor_active", "torque_limited", "pivot_displacement_mm",
)


def proposal_changes(before: dict, after: dict) -> list[dict]:
    """Compare settings, never the prose or generated candidate identifiers."""
    changes = []
    if before["family"] != after["family"]:
        changes.append({"parameter": "family", "before": before["family"], "after": after["family"]})
    for group in ("parameters", "control"):
        for key, value in after.get(group, {}).items():
            old = before.get(group, {}).get(key)
            if old != value:
                changes.append({"parameter": key, "before": old, "after": value})
    return changes


def extract(workspace: Path) -> dict:
    sources = {}

    def read(relative):
        path = workspace / relative
        raw = path.read_bytes()
        sources[str(relative)] = {"path": str(relative), "sha256": hashlib.sha256(raw).hexdigest(),
                                  "bytes": len(raw)}
        return json.loads(raw)

    history = read("balancing-cube-simulation/gpu-results-final/report/analysis.json")
    data = {"schema_version": 2, "evidence_cut": "2026-10-12", "article_revision": "2026-10-17", "runs": [],
            "historical": {"candidate_count": history["overview"]["candidate_count"],
                           "exploration_all_pass": history["overview"]["counts"]["exploration_all_pass"],
                           "trial_count": history["failure_analysis"]["exploration"]["trials"],
                           "prior46": history["prior46"]["status_counts"],
                           "scope": "Historical evaluator and adjudication; separate from fixed-dt runs"}}
    # The displayed model follows One-Piece's reviewed release. Archived runs
    # below still identify the exact requirements they actually consumed.
    from .system_model import load_system_model
    data['system_model'], model_sources = load_system_model(workspace, MODEL_REVISION)
    sources.update(model_sources)
    for name in RUNS:
        base = Path("engineering_agents/src/experiments/results") / name
        summary = read(base / "summary.json")
        manifest = read(base / "execution-manifest.json")
        prep_name = "memory10" if summary["iterations_completed"] == 10 else "memory20"
        preparation = read(f"integration-validation/ea-qwen27b-{prep_name}-preparation-20261012.json")
        snapshot = read(base / "frozen-snapshot.json")
        validation = read(base / "validation/result.json")
        compiled = read(base / "validation/compiled.json")
        first_context = read(base / "round-01/ssot-context.json")
        reference = next(r for r in first_context["records"] if
                         {"id": r["id"], "revision": r["revision"]} == snapshot["comparison_design_ref"])

        def resolved_settings(proposal):
            # The archive uses family=reference with an empty parameter object
            # for cached factorial cells. Resolve that alias from its exact
            # One-Piece design, not by treating absent values as design edits.
            return {"family": reference["data"]["family"] if proposal["family"] == "reference" else proposal["family"],
                    "parameters": reference["data"]["parameters"] if proposal["family"] == "reference" else proposal["parameters"],
                    "control": {"tilt_q_scale": 1.0, "rate_q_scale": 1.0, "momentum_q_scale": 1.0,
                                "yaw_rate_gain_nm_s": snapshot["controller"]["yaw_rate_gain_nm_s"],
                                **proposal.get("control", {})}}
        candidates = []
        for path in sorted((workspace / base / "candidates").glob("*/result.json")):
            result = read(path.relative_to(workspace))
            proposal = read(path.with_name("compiled.json").relative_to(workspace))
            candidates.append({k: result[k] for k in (
                "candidate_id", "round", "matrix_cell", "score", "screening_pass_fraction",
                "all_screening_passed", "numeric_gpu_verified", "controller_digest", "input_digest")})
            candidates[-1].update(proposal=proposal["proposal"],
                                  source=path.relative_to(workspace).as_posix(),
                                  failure_metrics=sorted({c["metric"] for r in result["records"]
                                                         for c in r["screening"] if not c["passed"]}),
                                  failed_case_count=sum(not all(g["passed"] for g in r["screening"])
                                                        for r in result["records"]),
                                  mean_final_tilt_rms_deg=sum(r["summary"]["final_1s_tilt_rms_deg"]
                                                             for r in result["records"]) / len(result["records"]))
        rounds = []
        for round_no in range(summary["iterations_completed"] + 1):
            seen = [c for c in candidates if c["round"] <= round_no]
            rounds.append({"round": round_no, "best_score": max(c["score"] for c in seen)})
        cases = []
        for record in validation["records"]:
            cases.append({"domain": record["domain_id"], "condition": record["condition_id"],
                          "seed": record["seed"], "status": record["summary"]["status"],
                          "passed": all(c["passed"] for c in record["screening"]),
                          "failures": [c for c in record["screening"] if not c["passed"]],
                          "agreement": record["paired_metrics"]["state"],
                          "summary": record["summary"]})
        # Matched stress case, not a synthesized animation. Retain every recorded
        # pose through termination, with no extrapolation after an early stop.
        replays = []
        for domain, condition, seed in (("heavy-delay-prior-confirm", "confirm-b", 812),
                                        ("heavy-delay-prior-confirm", "confirm-b", 811),
                                        ("nominal-prior-confirm", "confirm-a", 811)):
            record = next(r for r in validation["records"] if
                          (r["domain_id"], r["condition_id"], r["seed"]) == (domain, condition, seed))
            replays.append({"frames": [{k: f[k] for k in REPLAY_FIELDS} for f in record["frames"]],
                           "physics": compiled["config"]["physics"],
                           "actuation": compiled["config"]["actuation"],
                           "corner_radius_m": record["summary"]["contact_corner_radius_m"],
                           "source": (base / "validation/result.json").as_posix(),
                           "case": f"{domain} / {condition} / seed {seed}",
                           "origin": "recorded native MuJoCo CPU validation poses",
                           "summary": record["summary"],
                           "status": record["summary"]["status"]})
        experiments = []
        for round_no in range(1, summary["iterations_completed"] + 1):
            folder = base / f"round-{round_no:02d}"
            prompt = read(folder / "prompt-data.json")
            proposal = read(folder / "proposal.json")
            memory = prompt["agent_memory"]
            experiments.append({"round": round_no, "proposal": proposal,
                                "changes_from_prompt_best": proposal_changes(resolved_settings(prompt["current_best"]["proposal"]),
                                                                             resolved_settings(proposal)),
                                "change_basis": "prompt current_best; reference aliases resolved from exact One-Piece comparison design",
                                "prior_best_score": prompt["current_best"]["feedback"]["score"],
                                "memory_episode_count": memory["episode_count"],
                                "memory_selected_count": memory["selected_count"],
                                "retrieved_evidence": [{k: e[k] for k in ("episode_id", "run_id", "round", "selection_reasons", "measured_feedback")}
                                                       for e in memory["episodic_memory"]],
                                "source": (folder / "prompt-data.json").as_posix()})
        data["runs"].append({"name": name, "run_id": summary["run_id"],
            "rounds_completed": summary["iterations_completed"],
            "candidate_count": summary["candidates_evaluated"],
            "wall_time_s": summary["wall_time_s"], "status": summary["status"],
            "selection_status": summary["selection_status"],
            "best": summary["best"], "validation": summary["validation"],
            "rounds": rounds, "candidates": candidates, "cases": cases, "replay": replays[0],
            "replays": replays, "experiments": experiments,
            "test_matrix": {k: snapshot["plan"][k] for k in ("exploration", "validation")},
            "frozen_requirement_refs": snapshot["context_refs"]["requirements"],
            "frozen_kdps": snapshot["kdps"]["entries"],
            "best_proposal": compiled["proposal"], "best_config": compiled["config"],
            "comparison_design": {"id": reference["id"], "revision": reference["revision"],
                                  "parameters": reference["data"]["parameters"], "family": reference["data"]["family"]},
            "llm": manifest["llm"], "model_root": preparation["verified_model_root"],
            "gpu_assignment": manifest["gpu_assignment"],
            "snapshot_ref": snapshot["source_snapshot_ref"],
            "screening": snapshot["contract"]["screening"],
            "summary_source": (base / "summary.json").as_posix(),
            "report": (base / "memory-pipeline-report.html").as_posix()})
    interrupted = read("engineering_agents/src/experiments/results/qwen27b-memory10-20261012/summary.json")
    data["interrupted"] = {k: interrupted[k] for k in ("status", "iterations_completed", "stopped_reason")}
    data["sources"] = list(sources.values())
    # Cross-check the extract at generation time. Fail instead of publishing
    # a plausible article about a partial or unexpectedly different archive.
    assert data["historical"]["candidate_count"] == 2048
    assert sum(data["historical"]["prior46"].values()) == 46
    for run, expected in zip(data["runs"], (13, 24)):
        assert len(run["candidates"]) == run["candidate_count"] == expected
        assert len(run["cases"]) == 12
        assert max(c["score"] for c in run["candidates"]) == run["best"]["score"]
        assert sum(c["passed"] for c in run["cases"]) == 11
        assert not run["best"]["half_step_adjudication_performed"]
    from .recent import extend
    return extend(workspace, data)


def cube_poster(data: dict, language: str) -> str:
    """First-paint figure from the same saved lower-wheel pose as the replay."""
    replay = data["mounting"]["replays"][1]
    frame, physics = replay["frames"][0], replay["physics"]
    side = physics["cube_side_m"]
    w, x, y, z = frame["quaternion_wxyz"]

    def project(v):
        a, b, c = v
        position = frame["position_m"]
        p = [(1-2*y*y-2*z*z)*a+(2*x*y-2*z*w)*b+(2*x*z+2*y*w)*c+position[0],
             (2*x*y+2*z*w)*a+(1-2*x*x-2*z*z)*b+(2*y*z-2*x*w)*c+position[1],
             (2*x*z-2*y*w)*a+(2*y*z+2*x*w)*b+(1-2*x*x-2*y*y)*c+position[2]]
        return 310+(p[0]-p[1])*.7071*1120, 370-(p[2]*.94-(p[0]+p[1])*.242)*1120

    def points(vertices):
        return " ".join(f"{a:.3f},{b:.3f}" for a, b in map(project, vertices))

    title = "下側3面のRWで頂点に立つCube：保存された初期姿勢" if language == "ja" else "Cube on one corner with three lower reaction wheels: recorded initial pose"
    svg = [f'<svg viewBox="0 0 620 450" role="img" aria-label="{title}">',
           '<rect width="620" height="450" fill="#f3f4ee"/>',
           '<path d="M50 370H570" stroke="#b5c0bd"/>']
    vertices = [[a*side, b*side, c*side] for a in range(2) for b in range(2) for c in range(2)]
    for face in ((0, 1, 3, 2), (0, 1, 5, 4), (0, 2, 6, 4), (7, 3, 1, 5), (7, 6, 4, 5), (7, 3, 2, 6)):
        svg.append(f'<polygon points="{points([vertices[i] for i in face])}" fill="#24566d" fill-opacity=".035"/>')
    for a in range(8):
        for b in range(a+1, 8):
            if sum(i != j for i, j in zip(vertices[a], vertices[b])) == 1:
                svg.append(f'<polyline points="{points([vertices[a], vertices[b]])}" stroke="#24566d" stroke-width="3"/>')
    for axis in range(3):
        center = [side/2]*3
        center[axis] = physics["wheel_face_inset_m"]
        ring = []
        for i in range(65):
            angle = i*math.pi/32
            p = center.copy()
            p[(axis+1) % 3] += physics["wheel_radius_m"]*math.cos(angle)
            p[(axis+2) % 3] += physics["wheel_radius_m"]*math.sin(angle)
            ring.append(p)
        svg.append(f'<polyline points="{points(ring)}" fill="none" stroke="#b64628" stroke-width="7" stroke-opacity=".7"/>')
        for i in range(3):
            angle = frame["wheel_angle_rad"][axis]+i*math.pi*2/3
            end = center.copy()
            end[(axis+1) % 3] += physics["wheel_radius_m"]*math.cos(angle)
            end[(axis+2) % 3] += physics["wheel_radius_m"]*math.sin(angle)
            svg.append(f'<polyline points="{points([center, end])}" stroke="#b64628" stroke-width="2"/>')
    svg.append('<circle cx="310" cy="370" r="5" fill="#276354"/></svg>')
    return "".join(svg)


def render(data: dict, copy: dict, language: str, output: Path, workspace: Path) -> str:
    text = copy[language]
    esc = html.escape
    section_map = {s["id"]: s for s in text["sections"]}
    template = (HERE / "template.html").read_text()
    template = template.replace("@@RECENT_SECTIONS@@", (HERE / "recent_sections.html").read_text())
    template = template.replace("@@RECENT_SCRIPT@@", (HERE / "recent.js").read_text())
    template = template.replace("@@SYSTEM_MODEL_SCRIPT@@", (HERE / "system_model.js").read_text())
    replacements = {"LANG": language, "TITLE": esc(text["title"]),
                    "SUBTITLE": esc(text["subtitle"]), "ABSTRACT": esc(text["abstract"]),
                    "CUBE_POSTER": cube_poster(data, language)}
    for key, section in section_map.items():
        replacements[key.upper() + "_TITLE"] = esc(section["title"])
        replacements[key.upper() + "_PROSE"] = "\n".join(f"<p>{esc(p)}</p>" for p in section["paragraphs"])
    replacements["HYPOTHESES"] = "\n".join(
        f'<li><h3>{esc(x["title"])}</h3><p>{esc(x["claim"])}</p><p class="finding">{esc(x["result"])}</p></li>'
        for x in text["hypotheses"])
    replacements["NEXT_EXPERIMENTS"] = "\n".join(
        f'<li><h3>{esc(x["title"])}</h3><p>{esc(x["method"])}</p><p class="finding">{esc(x["criterion"])}</p></li>'
        for x in text["next_experiments"])
    replacements["GLOSSARY"] = "\n".join(
        f'<dt>{esc(x["term"])}</dt><dd>{esc(x["definition"])}</dd>' for x in text["glossary"])
    # Only the evidence payload is shared between reading languages. Original
    # JSON values, identity and hashes do not change with translation.
    replacements["EVIDENCE"] = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    replacements["UI"] = json.dumps(text.get("ui", {}), ensure_ascii=False).replace("<", "\\u003c")
    replacements["OTHER_LANG"] = "日本語" if language == "en" else "English"
    replacements["OTHER_FILE"] = "index.ja.html" if language == "en" else "index.html"
    replacements["WORKSPACE_BASE"] = json.dumps(os.path.relpath(workspace, output.parent).replace(os.sep, "/") + "/")
    for path, token in [
        ("reports/en/index.html" if language == "en" else "reports/ja/index.html", "CATALOG"),
        ("one-piece/projects/balancing-cube/report/index.html", "MODEL_REPORT"),
        ("balancing-cube-simulation/gpu-results-final/report/index.html", "HISTORY_REPORT"),
        ("balancing-cube-simulation/gpu-results-final/gnc-report/index.html", "GNC_REPORT"),
        ("engineering_agents/src/experiments/results/pr82-onepiece-mujoco-loop-20261011-iteration4/pipeline-report.html", "LOCAL_REPORT"),
    ]:
        replacements[token] = quote(os.path.relpath(workspace / path, output.parent).replace(os.sep, "/"), safe="/.-_")
    for token, value in replacements.items():
        template = template.replace("@@" + token + "@@", value)
    figure = 0

    def number_figure(match):
        nonlocal figure
        figure += 1
        label = f"Figure {figure}. " if language == "en" else f"図{figure}. "
        return f'<span class="fig-number">{label}</span>'

    template = re.sub(r'<span class="fig-number"[^>]*>.*?</span>', number_figure, template)
    if "@@" in template:
        raise ValueError("Unfilled article token")
    return template


def build(workspace: Path, output: Path, *, refresh=False, register=False) -> list[Path]:
    if refresh:
        data = extract(workspace)
        # Keep the frozen machine extract compact in PRs. The built article
        # writes an indented copy beside the HTML for human inspection.
        (HERE / "evidence.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    else:
        data = json.loads((HERE / "evidence.json").read_text())
    copy = json.loads((HERE / "copy.json").read_text())
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for lang, name in (("en", "index.html"), ("ja", "index.ja.html")):
        path = output / name
        path.write_text(render(data, copy, lang, path, workspace), encoding="utf-8")
        paths.append(path)
    (output / "evidence.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    if register:
        from tools.report_library import catalog, translate_reports
        manifest_path = workspace / "reports/translation_manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"schema_version": 1, "entries": {}}
        filename = "balancing-cube-research-story.html"
        localized = {}
        for lang, source in zip(("en", "ja"), paths):
            destination = workspace / "reports" / lang / "items" / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(translate_reports.reading_copy(source.read_text(), paths[0], destination,
                                   lang, {}, lang), encoding="utf-8")
            localized[lang] = destination.relative_to(workspace).as_posix()
        # One catalog source owns both languages. The Japanese native original
        # remains discoverable as a translation source, not a second report.
        manifest["entries"].pop(paths[1].relative_to(workspace).as_posix(), None)
        manifest["entries"][paths[0].relative_to(workspace).as_posix()] = {
            "source_language": "en", "source_sha256": hashlib.sha256(paths[0].read_bytes()).hexdigest(),
            **localized, "reading_sources": {k: p.relative_to(workspace).as_posix() for k, p in zip(("en", "ja"), paths)}}
        catalog.atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        catalog.build_catalog()
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    os.environ["EA_REPORT_WORKSPACE"] = str(workspace)
    output = args.output or workspace / "engineering_agents/src/experiments/results/balancing-cube-research-story-20261012"
    for path in build(workspace, output.resolve(), refresh=args.refresh, register=args.register):
        print(path)


if __name__ == "__main__":
    main()
