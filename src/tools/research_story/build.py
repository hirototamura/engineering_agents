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
import os
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).parent
RUNS = ("qwen27b-memory10-20261012-r2", "qwen27b-memory20-20261012")


def extract(workspace: Path) -> dict:
    sources = {}

    def read(relative):
        path = workspace / relative
        raw = path.read_bytes()
        sources[str(relative)] = {"path": str(relative), "sha256": hashlib.sha256(raw).hexdigest(),
                                  "bytes": len(raw)}
        return json.loads(raw)

    history = read("balancing-cube-simulation/gpu-results-final/report/analysis.json")
    data = {"schema_version": 1, "evidence_cut": "2026-10-12", "runs": [],
            "historical": {"candidate_count": history["overview"]["candidate_count"],
                           "exploration_all_pass": history["overview"]["counts"]["exploration_all_pass"],
                           "trial_count": history["failure_analysis"]["exploration"]["trials"],
                           "prior46": history["prior46"]["status_counts"],
                           "scope": "Historical evaluator and adjudication; separate from fixed-dt runs"}}
    for name in RUNS:
        base = Path("engineering_agents/src/experiments/results") / name
        summary = read(base / "summary.json")
        manifest = read(base / "execution-manifest.json")
        prep_name = "memory10" if summary["iterations_completed"] == 10 else "memory20"
        preparation = read(f"integration-validation/ea-qwen27b-{prep_name}-preparation-20261012.json")
        snapshot = read(base / "frozen-snapshot.json")
        validation = read(base / "validation/result.json")
        compiled = read(base / "validation/compiled.json")
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
                                                         for c in r["screening"] if not c["passed"]}))
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
        stress = next(r for r in validation["records"] if
                      r["domain_id"] == "heavy-delay-prior-confirm" and
                      r["condition_id"] == "confirm-b" and r["seed"] == 812)
        replay = {"frames": [{k: f[k] for k in (
            "time_s", "position_m", "quaternion_wxyz", "wheel_angle_rad", "tilt_total_deg")}
                              for f in stress["frames"]],
                  "physics": compiled["config"]["physics"],
                  "corner_radius_m": stress["summary"]["contact_corner_radius_m"],
                  "source": (base / "validation/result.json").as_posix(),
                  "case": "heavy-delay-prior-confirm / confirm-b / seed 812",
                  "origin": "recorded native MuJoCo CPU validation poses",
                  "status": stress["summary"]["status"]}
        data["runs"].append({"name": name, "run_id": summary["run_id"],
            "rounds_completed": summary["iterations_completed"],
            "candidate_count": summary["candidates_evaluated"],
            "wall_time_s": summary["wall_time_s"], "status": summary["status"],
            "selection_status": summary["selection_status"],
            "best": summary["best"], "validation": summary["validation"],
            "rounds": rounds, "candidates": candidates, "cases": cases, "replay": replay,
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
    return data


def render(data: dict, copy: dict, language: str, output: Path, workspace: Path) -> str:
    text = copy[language]
    esc = html.escape
    section_map = {s["id"]: s for s in text["sections"]}
    template = (HERE / "template.html").read_text()
    replacements = {"LANG": language, "TITLE": esc(text["title"]),
                    "SUBTITLE": esc(text["subtitle"]), "ABSTRACT": esc(text["abstract"])}
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
