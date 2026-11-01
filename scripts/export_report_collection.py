"""Archive an existing report workspace with its indexed sources and page assets."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def export(workspace: Path, output: Path) -> dict:
    workspace = workspace.resolve()
    catalog = json.loads((workspace / 'reports/catalog.json').read_text())
    roots = {workspace / 'reports'}
    for row in catalog['entries']:
        source = workspace / row['path']
        # A top-level source file does not authorize its whole project tree.
        roots.add(source if len(source.relative_to(workspace).parts) <= 3 else source.parent)
    files = set()
    excluded = {'__pycache__', '.git', '.venv', 'node_modules', '.pytest_cache'}
    for root in roots:
        candidates = root.rglob('*') if root.is_dir() else [root]
        for path in candidates:
            rel = path.relative_to(workspace)
            if not path.is_file() or excluded.intersection(rel.parts):
                continue
            if path.name.startswith('.env') or path.suffix in {'.pyc', '.pem', '.key'}:
                continue
            if path.is_symlink():
                continue
            files.add(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(workspace).as_posix())
    digest = hashlib.sha256()
    with output.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'filename': output.name, 'sha256': digest.hexdigest(),
            'size_bytes': output.stat().st_size, 'files': len(files),
            'latest_main_reports': catalog['report_count'],
            'indexed_source_reports': catalog['indexed_report_count'],
            'indexed_html': catalog['all_html_count']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--metadata', type=Path)
    args = parser.parse_args()
    encoded = json.dumps(export(args.workspace, args.output), indent=2) + '\n'
    if args.metadata:
        args.metadata.write_text(encoded)
    print(encoded)
