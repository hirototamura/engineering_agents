"""Restore pinned companion repos and private Release evidence without overwriting work."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _legacy_tracks(archive):
    tracks = {}
    prefix = ("engineering_agents", "src", "experiments", "results")
    for item in archive.infolist():
        parts = PurePosixPath(item.filename).parts
        if parts[:4] == prefix and len(parts) == 6 and parts[-1] == "summary.json":
            if item.file_size > 2 * 1024 * 1024:
                raise ValueError("Legacy run summary exceeds migration size limit")
            summary = json.loads(archive.read(item))
            scenario = summary.get("scenario")
            if scenario in {"ssos_eclss_loop", "scrubber_degradation"}:
                tracks[parts[4]] = "eclss"
            elif scenario == "balancing_cube":
                tracks[parts[4]] = "balancing_cube"
            elif scenario is not None:
                raise ValueError(f"Unknown legacy experiment scenario: {scenario}")
    return tracks


def _current_path(rel, tracks):
    parts = rel.parts
    base = ("engineering_agents", "experiments")
    if parts[:4] == ("engineering_agents", "src", "experiments", "results"):
        if len(parts) == 4:
            return PurePosixPath(*base)
        run = parts[4]
        track = tracks.get(run)
        if track is None:
            if run in {"evaluation.html", ".gitkeep"} or run.startswith(("ssos", "scrubber", "review2-eclss", "plant-sim")):
                track = "eclss"
            elif run.startswith(("cube", "bottom", "pr82-onepiece", "qwen27b", "mass-inspired", "balancing-cube", "remrc")):
                track = "balancing_cube"
            else:
                raise ValueError(f"Cannot classify legacy experiment without summary.scenario: {run}")
        return PurePosixPath(*base, track, "results", *parts[4:])
    if parts[:4] == ("engineering_agents", "src", "experiments", "analysis"):
        return PurePosixPath(*base, "eclss", "analysis", *parts[4:])
    if parts[:2] == base and len(parts) >= 3 and parts[2] in {"analysis", "outputs", "runs"}:
        return PurePosixPath(*base, "eclss", *parts[2:])
    return rel


def restore_archive(archive_path, workspace):
    with zipfile.ZipFile(archive_path) as archive:
        tracks = _legacy_tracks(archive)
        resolved, targets = [], set()
        # Validate the entire archive before writing. Never follow an existing symlink.
        for item in archive.infolist():
            rel = PurePosixPath(item.filename)
            if rel.is_absolute() or ".." in rel.parts or "\\" in item.filename:
                raise ValueError(f"Unsafe archive path: {item.filename}")
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError(f"Archive symlink: {item.filename}")
            rel = _current_path(rel, tracks)
            if rel in targets:
                raise ValueError(f"Duplicate destination after experiment migration: {rel}")
            targets.add(rel)
            resolved.append((item, rel))
            target = workspace.joinpath(*rel.parts)
            if not target.resolve().is_relative_to(workspace.resolve()):
                raise ValueError(f"Path escapes workspace: {item.filename}")
            if any(p.is_symlink() for p in [target, *target.parents]):
                raise ValueError(f"Existing symlink: {item.filename}")
            if target.exists() and not item.is_dir():
                with archive.open(item) as stream:
                    expected = hashlib.file_digest(stream, "sha256").hexdigest()
                if sha(target) != expected:
                    raise FileExistsError(f"Preserve existing changed file: {target}")
        for item, rel in resolved:
            target = workspace.joinpath(*rel.parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("xb") as dest:
                    shutil.copyfileobj(source, dest)
        return {"migrated_paths": sum(str(rel) != item.filename for item, rel in resolved)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    lock = json.loads((HERE / "workspace.lock.json").read_text())
    for repo in lock["repositories"]:
        target = workspace / repo["directory"]
        if target.exists():
            if run("git", "-C", str(target), "rev-parse", "HEAD") != repo["revision"]:
                raise RuntimeError(f"Existing checkout is at another revision: {target}")
            if run("git", "-C", str(target), "status", "--porcelain", "--untracked-files=no"):
                raise RuntimeError(f"Existing checkout has tracked changes: {target}")
        else:
            run("gh", "repo", "clone", repo["github"], str(target))
            run("git", "-C", str(target), "checkout", "--detach", repo["revision"])
    if args.source_only:
        return
    cache = workspace / ".runtime" / "evidence-downloads"
    cache.mkdir(parents=True, exist_ok=True)
    evidence = lock["evidence"]
    for asset in json.loads((HERE / evidence["manifest"]).read_text())["assets"]:
        path = cache / asset["name"]
        if not path.exists():
            run("gh", "release", "download", evidence["release"], "-R", evidence["repository"],
                "--pattern", asset["name"], "--dir", str(cache))
        if sha(path) != asset["sha256"]:
            raise ValueError(f"Checksum mismatch: {path}")
        receipt = restore_archive(path, workspace)
        print(f"Verified and restored {asset['name']} ({receipt['migrated_paths']} migrated experiment paths)", flush=True)


if __name__ == "__main__":
    main()
