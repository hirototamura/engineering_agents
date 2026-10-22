"""Create private, checksummed workspace evidence packs; never include credentials."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

PACKS = {
    "engineering-agents-results": ["engineering_agents/src/experiments/results"],
    "onepiece-evidence-objects": ["one-piece/projects/balancing-cube/store/commits"],
    "cube-results": ["balancing-cube-simulation/results"],
    "research-reports": ["reports"],
    "cad-source-inputs": ["Self balancing cube (cubli) - 6695891", "Self_Balancing_Cube_BOM.xlsx"],
    "website-cad": ["engineering_agents/website/public/cube-cad"],
    "downloadable-archives": ["engineering_agents/src/experiments/results", "balancing-cube-simulation/results", "reports"],
}


def allowed(path: Path) -> bool:
    return not any(part in {".git", "__pycache__", ".DS_Store", ".vercel", "node_modules"}
                   or part.startswith((".env", ".venv")) for part in path.parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "visibility": "private", "assets": []}
    for name, roots in PACKS.items():
        dest = args.output / (name + ".zip")
        count = 0
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
            for root in roots:
                source = args.workspace / root
                if not source.exists():
                    raise FileNotFoundError(source)
                for path in sorted(source.rglob("*")) if source.is_dir() else [source]:
                    rel = path.relative_to(args.workspace)
                    if not path.is_file() or path.is_symlink() or not allowed(rel):
                        continue
                    if name == "onepiece-evidence-objects" and "objects" not in rel.parts:
                        continue  # Canonical records are in Git; indexes are rebuilt.
                    if (path.suffix in {".zip", ".gz"}) != (name == "downloadable-archives"):
                        continue  # Keep original downloadable files in a separate pack.
                    archive.write(path, rel.as_posix())
                    count += 1
        with dest.open("rb") as stream:
            sha = hashlib.file_digest(stream, "sha256").hexdigest()
        entry = {"name": dest.name, "sha256": sha, "size": dest.stat().st_size, "files": count}
        manifest["assets"].append(entry)
        print(json.dumps(entry), flush=True)
    (args.output / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
