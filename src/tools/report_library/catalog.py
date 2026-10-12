#!/usr/bin/env python3
"""Build and serve a local, searchable catalog of workspace HTML reports.

The catalog is a derived index. It never edits source reports. Run ``build`` for
an offline snapshot, or ``serve`` for discovery whenever the page is refreshed.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import html
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from urllib.parse import quote, unquote, urlsplit
import webbrowser


from .paths import HERE, WORKSPACE
TEMPLATE = Path(__file__).with_name("catalog_template.html")
OUTPUT = HERE / "index.html"
DATA = HERE / "catalog.json"
MANIFEST = HERE / "translation_manifest.json"
THUMBNAILS = HERE / "thumbnail_manifest.json"
LANG_OUTPUTS = {language: HERE / language / "index.html" for language in ("en", "ja")}
TITLE = re.compile(r"<title\b[^>]*>(.*?)</title\s*>", re.IGNORECASE | re.DOTALL)
SKIP_NAMES = {
    ".git", ".venv", ".venv-integration", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", "site-packages", ".next", ".cache",
    "build", "dist",
}


def report_paths() -> list[Path]:
    """Include ignored run artifacts but omit dependencies and this catalog."""
    command = [
        "rg", "--files", "-uuu", "-g", "*.html", "-g", "*.htm",
        "-g", "!**/.git/**", "-g", "!**/.venv*/**",
        "-g", "!**/node_modules/**", "-g", "!**/site-packages/**",
        "-g", "!**/store/commits/**", "-g", "!reports/**",
        "-g", "!**/src/tools/report_library/**",
        "-g", "!**/build/**", "-g", "!**/dist/**",
    ]
    try:
        result = subprocess.run(command, cwd=WORKSPACE, capture_output=True,
                                text=True, check=True)
        relative = [Path(line) for line in result.stdout.splitlines()]
    except (FileNotFoundError, subprocess.CalledProcessError):
        relative = []
        for base, dirs, files in os.walk(WORKSPACE):
            dirs[:] = [name for name in dirs if name not in SKIP_NAMES
                       and not name.startswith(".venv") and name != "store"
                       and Path(base, name) not in {HERE, Path(__file__).parent}]
            for name in files:
                if name.lower().endswith((".html", ".htm")):
                    relative.append(Path(base, name).relative_to(WORKSPACE))
    return sorted({WORKSPACE / path for path in relative
                   if path.parts and path.parts[0] != "reports"})


def read_title(path: Path) -> str:
    try:
        with path.open("rb") as source:
            head = source.read(65536).decode("utf-8", errors="replace")
    except OSError:
        return path.stem.replace("-", " ").replace("_", " ").title()
    match = TITLE.search(head)
    if match:
        title = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", match[1]))).strip()
        if title:
            return title
    return path.stem.replace("-", " ").replace("_", " ").title()


def classify(relative: Path, title: str) -> dict:
    path = relative.as_posix()
    name = relative.name.lower()
    project = {
        "engineering_agents": "Engineering Agents",
        "one-piece": "One-Piece",
        "balancing-cube-simulation": "Balancing Cube",
        "balancing-cube-pre-research": "Cube Research",
        "integration-validation": "Integration Evidence",
    }.get(relative.parts[0], relative.parts[0].replace("-", " ").title())
    category, family, description, scope = "Other report", "Other reports", "HTML artifact from this workspace.", "report"

    if path.startswith("engineering_agents/site/"):
        category, family, description, scope = "Documentation", "Published documentation", "Generated documentation page.", "documentation"
    elif path.startswith("integration-validation/") or "/report/assets/" in path or "/pr82-publish-smoke-" in path:
        category, family, description, scope = "Archived copy", "Archived evidence", "Stored copy of an earlier report.", "archive"
    elif path.startswith("balancing-cube-simulation/tools/") or "/report/code/tools/" in path:
        category, family, description, scope = "Source template", "Report sources", "HTML source used to create a report.", "source"
    elif "memory-pipeline-report" in name:
        category, family = "Design iterations", "Qwen design iterations"
        description = "Qwen proposals, MuJoCo CPU/GPU trials, memory, validation, and One-Piece evidence."
    elif "agent-harness-guide" in name:
        category, family = "Agent workflow", "Agent harness"
        description = "The simulation agent harness and its evidence flow."
    elif "pipeline-report" in name:
        category, family = "Design iterations", "PR 82 design loop"
        description = "One-Piece context, Engineering Agents proposals, MuJoCo trials, and feedback."
    elif path.startswith("one-piece/projects/balancing-cube/report/"):
        category, family = "System model", "One-Piece cube model"
        description = "Versioned requirements, parameters, trace links, design, and verification evidence."
    elif "gnc-report" in path or "gnc_report" in name:
        category, family = "GNC", "Cube GNC"
        description = "Sensors, attitude estimation, guidance, and control for the balancing cube."
    elif "gpu-results" in path or "gpu-campaign" in path or "gpu_results" in name:
        category, family = "GPU exploration", "Cube GPU exploration"
        description = "GPU design search, CPU confirmation, simulation evidence, and replay."
    elif path.startswith("balancing-cube-pre-research/") or "research-plan" in name:
        category, family = "Research", "Cube research"
        description = "Research and development studies that preceded the current design loop."
    elif "evaluation" in name or "scorecard" in name:
        category, family = "ECLSS evaluation", "ECLSS evaluation"
        description = "ECLSS simulation or verification results."
    elif "design_loop_analysis" in name:
        category, family = "Engineering analysis", "Design loop analysis"
        description = "Analysis of design iteration and simulation feedback."

    return {"project": project, "category": category, "family": family,
            "description": description, "scope": scope}


def run_details(relative: Path) -> dict:
    if relative.name != "memory-pipeline-report.html":
        return {}
    summary = WORKSPACE / relative.parent / "summary.json"
    try:
        data = json.loads(summary.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    best, validation = data.get("best") or {}, data.get("validation") or {}
    total = validation.get("trial_count")
    fraction = validation.get("screening_pass_fraction")
    passes = round(total * fraction) if isinstance(total, int) and isinstance(fraction, (int, float)) else None
    return {
        "run_id": data.get("run_id"),
        "rounds": data.get("iterations_completed"),
        "candidates": data.get("candidates_evaluated"),
        "best_score": best.get("score"),
        "validation_score": validation.get("score"),
        "validation_passes": passes,
        "validation_total": total,
        "selection_status": data.get("selection_status"),
        "numeric_gpu_verified": validation.get("numeric_gpu_verified"),
    }


def current_revision(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in [TEMPLATE, MANIFEST, THUMBNAILS, Path(__file__), *paths]:
        try:
            stat = path.stat()
        except OSError:
            continue
        digest.update(f"{path}\0{stat.st_mtime_ns}\0{stat.st_size}\n".encode())
        if path.name == "memory-pipeline-report.html":
            try:
                sidecar = (path.parent / "summary.json").stat()
                digest.update(f"{sidecar.st_mtime_ns}\0{sidecar.st_size}\n".encode())
            except OSError:
                pass
    return digest.hexdigest()


def atomic_write(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix="." + path.name + ".", suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def mark_latest_reports(entries: list[dict]) -> None:
    """Group source/localized title aliases; keep one newest report per group."""
    reports = [row for row in entries if row["scope"] == "report"]
    parents = list(range(len(reports)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    titles = {}
    for index, row in enumerate(reports):
        for title in [row["title"], *row.get("localized_titles", {}).values()]:
            key = " ".join(unicodedata.normalize("NFKC", title).casefold().split())
            if not key:
                continue
            if key in titles:
                parents[find(index)] = find(titles[key])
            else:
                titles[key] = index
    groups = {}
    for index, row in enumerate(reports):
        groups.setdefault(find(index), []).append(row)
    for group in groups.values():
        newest = min(group, key=lambda row: (-row["modified_ns"], row["path"]))
        for row in group:
            row["latest_report"] = row is newest
            row["version_count"] = len(group)
            row.pop("superseded_by", None)
            if row is not newest:
                row["superseded_by"] = newest["path"]


def build_catalog() -> dict:
    HERE.mkdir(parents=True, exist_ok=True)
    for source in Path(__file__).with_name("launchers").glob("*"):
        destination = HERE / source.name
        if not destination.exists():
            atomic_write(destination, source.read_text(encoding="utf-8"))
            if source.suffix == ".command":
                destination.chmod(0o755)
    paths = report_paths()
    revision = current_revision(paths)
    try:
        existing = json.loads(DATA.read_text(encoding="utf-8"))
        if existing.get("revision") == revision and OUTPUT.is_file() and all(path.is_file() for path in LANG_OUTPUTS.values()):
            return existing
    except (OSError, ValueError):
        pass

    try:
        translations = json.loads(MANIFEST.read_text(encoding="utf-8")).get("entries", {})
    except (OSError, ValueError):
        translations = {}
    try:
        thumbnails = json.loads(THUMBNAILS.read_text(encoding="utf-8")).get("entries", {})
    except (OSError, ValueError):
        thumbnails = {}
    entries = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        relative = path.relative_to(WORKSPACE)
        title = read_title(path)
        info = classify(relative, title)
        entry = {
            "id": hashlib.sha256(relative.as_posix().encode()).hexdigest()[:12],
            "path": relative.as_posix(),
            "href": "../" + quote(relative.as_posix(), safe="/-_.~"),
            "title": title,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            "modified_ns": stat.st_mtime_ns,
            "size_bytes": stat.st_size,
            **info,
            "run": run_details(relative),
        }
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest() if info["scope"] == "report" else None
        matching = translations.get(relative.as_posix(), {})
        if source_hash and matching.get("source_sha256") == source_hash:
            localized = {language: matching[language] for language in ("en", "ja")
                         if matching.get(language) and (WORKSPACE / matching[language]).is_file()}
            entry["localized"] = localized
            entry["localized_titles"] = {
                language: read_title(WORKSPACE / page)
                for language, page in localized.items()
            }
        entry["source_language"] = matching.get("source_language") if matching else None
        previews = {}
        for language in ("en", "ja"):
            capture_path = entry.get("localized", {}).get(language, relative.as_posix())
            preview = thumbnails.get(capture_path, {})
            try:
                capture_stat = (WORKSPACE / capture_path).stat()
                if (preview.get("source_modified_ns") == capture_stat.st_mtime_ns
                        and preview.get("source_size_bytes") == capture_stat.st_size
                        and preview.get("image") and (WORKSPACE / preview["image"]).is_file()):
                    previews[language] = preview["image"]
            except OSError:
                pass
        entry["thumbnails"] = previews
        entries.append(entry)
    entries.sort(key=lambda row: (-row["modified_ns"], row["path"]))
    mark_latest_reports(entries)
    collection = {
        "schema_version": 3,
        "revision": revision,
        "indexed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "workspace": str(WORKSPACE),
        "report_count": sum(row.get("latest_report", False) for row in entries),
        "indexed_report_count": sum(row["scope"] == "report" for row in entries),
        "all_html_count": len(entries),
        "entries": entries,
    }
    encoded = json.dumps(collection, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count("__REPORT_CATALOG_DATA__") != 1 or template.count("__CATALOG_LANGUAGE__") != 2:
        raise ValueError("Catalog template must contain one data placeholder")
    atomic_write(DATA, json.dumps(collection, ensure_ascii=False, indent=2) + "\n")
    for language, output in LANG_OUTPUTS.items():
        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(output, template.replace("__REPORT_CATALOG_DATA__", encoded)
                     .replace("__CATALOG_LANGUAGE__", language))
    atomic_write(OUTPUT, '<!doctype html><html lang="en"><meta charset="utf-8">'
                 '<title>Engineering Report Library / 技術レポート一覧</title>'
                 '<script>let l="en";try{l=localStorage.getItem("report-language")==="ja"?"ja":"en"}catch(e){}'
                 'location.replace(l+"/index.html"+location.search)</script>'
                 '<p><a href="en/index.html">English</a> · <a href="ja/index.html">日本語</a></p></html>')
    return collection


def serve(port: int, open_browser: bool) -> None:
    build_catalog()
    preview_process = None
    last_preview_attempt = 0.0
    preview_lock = threading.Lock()

    def update_previews(collection: dict) -> None:
        nonlocal preview_process, last_preview_attempt
        if all(set(row.get("thumbnails", {})) == {"en", "ja"} for row in collection["entries"]):
            return
        with preview_lock:
            if preview_process is not None and preview_process.poll() is None:
                return
            if time.monotonic() - last_preview_attempt < 60:
                return
            last_preview_attempt = time.monotonic()
            preview_process = subprocess.Popen(
                [sys.executable, "-m", "tools.report_library", "--workspace", str(WORKSPACE), "capture"], cwd=WORKSPACE)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(WORKSPACE), **kwargs)

        def log_message(self, format: str, *args) -> None:
            return

        def _allowed_request(self) -> bool:
            route = unquote(urlsplit(self.path).path)
            if route == "/":
                self.send_response(302)
                self.send_header("Location", "/reports/index.html")
                self.end_headers()
                return False
            if route in {"/reports/index.html", "/reports/en/index.html", "/reports/ja/index.html", "/reports/catalog.json"}:
                update_previews(build_catalog())
            relative = Path(route.lstrip("/"))
            if relative.is_absolute() or ".." in relative.parts or any(part.startswith(".") for part in relative.parts):
                self.send_error(403)
                return False
            if relative.parts[:2] == ("reports", "thumbnails"):
                if relative.suffix != ".webp":
                    self.send_error(403)
                    return False
                return True
            if relative not in {Path("reports/index.html"), Path("reports/en/index.html"),
                                Path("reports/ja/index.html"), Path("reports/catalog.json")}:
                catalog = build_catalog()
                direct = {Path(entry["path"]) for entry in catalog["entries"]}
                direct.update(Path(page) for entry in catalog["entries"]
                              for page in entry.get("localized", {}).values())
                parents = [path.parent for path in direct if path.parent != Path(".")]
                if relative not in direct and not any(relative.is_relative_to(parent) for parent in parents):
                    self.send_error(403)
                    return False
                if any(part in {".git", "store", ".venv", "node_modules"} for part in relative.parts):
                    self.send_error(403)
                    return False
            return True

        def do_GET(self) -> None:
            if self._allowed_request():
                super().do_GET()

        def do_HEAD(self) -> None:
            if self._allowed_request():
                super().do_HEAD()

    address = ("127.0.0.1", port)
    with ThreadingHTTPServer(address, Handler) as server:
        url = f"http://127.0.0.1:{port}/reports/index.html"
        print(f"Live report catalog: {url}", flush=True)
        print("New HTML files are discovered when this page is refreshed.", flush=True)
        if open_browser:
            webbrowser.open(url)
        server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("build", help="Refresh the offline HTML and JSON catalog")
    live = sub.add_parser("serve", help="Serve a live catalog that rescans on refresh")
    live.add_argument("--port", type=int, default=8765)
    live.add_argument("--open", action="store_true", help="Open the catalog in the default browser")
    args = parser.parse_args()
    if args.action == "build":
        result = build_catalog()
        print(f"{OUTPUT} — {result['report_count']} reports, {result['all_html_count']} HTML files")
    else:
        serve(args.port, args.open)


if __name__ == "__main__":
    main()
