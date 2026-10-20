"""Import an exact One-Piece model projection without re-running experiments."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path


def load_system_model(workspace: Path, revision: str | None = None) -> tuple[dict, dict]:
    records, origins = {}, {}
    for path in sorted((workspace / 'one-piece/projects/balancing-cube/store/commits').glob('*/records.json')):
        raw = path.read_bytes()
        source = {'path': path.relative_to(workspace).as_posix(),
                  'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        for record in json.loads(raw):
            key = (record['id'], record['revision'])
            if key in records and records[key] != record:
                raise ValueError(f'Conflicting One-Piece record: {key}')
            records[key], origins[key] = record, source
    models = [r for r in records.values() if r['id'] == 'cube.system-model.active'
              and r['kind'] == 'system_model' and (revision is None or r['revision'] == revision)]
    if not models:
        raise ValueError(f'No active system model for revision {revision!r}')
    model = max(models, key=lambda r: datetime.fromisoformat(r['created_at']))
    sources = {}

    def resolve(ref):
        key = (ref['id'], ref['revision'])
        if key not in records:
            raise ValueError(f'Missing exact model reference: {key}')
        source = origins[key]
        sources[source['path']] = source
        return records[key]

    resolve(model)
    snapshot = resolve(model['data']['simulation_snapshot_ref'])
    context = snapshot['data']['context_refs']
    projection = {'revision': model['revision'], 'source': origins[(model['id'], model['revision'])]['path'],
                  'profile': model['data'], 'model_record': model,
                  'snapshot_ref': {'id': snapshot['id'], 'revision': snapshot['revision']}}
    for field, context_field, kind in [('requirements', 'requirements', 'requirement'),
                                     ('parameters', 'kdps', 'parameter'),
                                     ('verification_cases', 'verification_cases', 'verification_case'),
                                     ('functions', 'functions', 'function'),
                                     ('products', 'products', 'product')]:
        selected = [resolve(ref) for ref in context.get(context_field, [])]
        if any(r['kind'] != kind for r in selected):
            raise ValueError(f'Unexpected record kind in {context_field}')
        projection[field] = sorted(selected, key=lambda r: r['id'])
    for field, ref_field in [('baseline', 'baseline_ref'), ('review_decision', 'review_decision_ref')]:
        ref = model['data'].get(ref_field)
        projection[field] = resolve(ref) if ref else None
    baseline = projection['baseline']
    if baseline:
        for member in baseline['data']['members']:
            body = resolve(member)
            canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
            if hashlib.sha256(canonical).hexdigest() != member['sha256']:
                raise ValueError(f'Baseline digest mismatch: {member["id"]}')
    return projection, sources


def refresh_model(data: dict, workspace: Path, revision: str | None = None) -> dict:
    """Replace the report's model only; archived campaign inputs stay pinned."""
    projection, sources = load_system_model(workspace, revision)
    source_index = {s['path']: s for s in data.get('sources', [])}
    result = {**data, 'system_model': projection, 'sources': list({**source_index, **sources}.values())}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--revision')
    parser.add_argument('--evidence', type=Path, default=Path(__file__).with_name('evidence.json'))
    args = parser.parse_args()
    data = refresh_model(json.loads(args.evidence.read_text()), args.workspace.resolve(), args.revision)
    args.evidence.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f'Imported One-Piece model {data["system_model"]["revision"]}; historical runs retained.')


if __name__ == '__main__':
    main()
