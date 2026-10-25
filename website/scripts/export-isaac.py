#!/usr/bin/env python3
"""Publish a bounded, lossless web projection of an audited Isaac analysis cache.

Run from the analysis environment. Large publication assets stay outside Git.
No GPU work, solver changes, or edits to historical measurements occur here.
"""
import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
import sys

import numpy as np

FIELDS = ['tilt_x_deg', 'tilt_y_deg', 'tilt_total_deg']
CASE_FIELDS = ['id', 'corner', 'initial_tilt_radius_deg', 'initial_tilt_x_deg', 'initial_tilt_y_deg',
               'initial_tilt_azimuth_deg', 'initial_yaw_rate_rad_s', 'seed', 'gpu_index', 'status', 'end_tick',
               'screening_passed', 'failed_metrics', 'simulated_duration_s', 'peak_tilt_deg',
               'final_1s_tilt_rms_deg', 'peak_wheel_rpm', 'peak_motor_torque_nm', 'contact_fraction',
               'peak_slip_speed_m_s', 'peak_pivot_displacement_mm', 'speed_governor_fraction']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False).encode()


def export(dataset, report, output):
    from tools.isaac_analysis.data import load
    from tools.isaac_analysis.statistics import quantiles, select
    data = load(dataset, verify=True)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'data').mkdir()
    (output / 'report').mkdir()
    files = {}

    def asset(name, raw):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(raw, compresslevel=6, mtime=0))
        value = {'url': '/isaac/' + name, 'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes()),
                 'uncompressed_bytes': len(raw), 'uncompressed_sha256': sha(raw)}
        files[name] = value
        return value

    groups = {}
    for label, group in data.catalog['groups'].items():
        if label not in ('reference', 'candidate'):
            raise ValueError('This publication targets the two named historical campaigns')
        factors = dict(group['factors'])
        # Include only exact scalar resolved values the bounded viewer exposes as filters.
        compiled = group['payload']['compiled']['config']
        physics = compiled['physics']
        sensing = compiled.get('sensing', {})
        factors.update({key: physics[key] for key in ('control_period_s', 'timestep_s', 'cube_side_m', 'frame_mass_kg', 'wheel_mass_kg', 'wheel_radius_m', 'wheel_axial_inertia_kg_m2', 'wheel_transverse_inertia_kg_m2', 'frame_inertia_kg_m2', 'wheel_thickness_m', 'wheel_face_inset_m', 'motor_torque_limit_nm', 'wheel_speed_limit_rad_s', 'gravity_m_s2') if key in physics})
        factors.update({key: sensing[key] for key in ('tilt_noise_std_deg', 'gyro_noise_std_deg_s') if key in sensing})
        factors['observation_delay_s'] = sensing.get('observation_delay_s', sensing.get('control_delay_s'))
        groups[label] = {'factors': factors, 'controller': group['payload']['compiled']['controller'],
                         'physics': group['payload']['compiled']['config']['physics'],
                         'sensing': group['payload']['compiled']['config'].get('sensing', {}),
                         'screening': group['payload']['snapshot']['contract']['screening'],
                         'input_digest': group['payload']['compiled']['input_digest'],
                         'plan_sha256': group['manifest']['plan_sha256'], 'plan_seed': group['plan_seed'],
                         'plan_distribution': group['plan_distribution'], 'trial_count': group['trial_count'],
                         'corners': {}, 'overviews': {}}
        for corner in (f'{i:03b}' for i in range(8)):
            indices = select(data, {'campaign': [label], 'corner': [corner]})
            rows = [{key: data.cases[i][key] for key in CASE_FIELDS} for i in indices]
            entry = {'count': len(indices), 'cases': asset(f'data/{label}-{corner}-cases.json.gz', encode(rows)), 'tilt': {}}
            for j, field in enumerate(FIELDS):
                raw = np.asarray(data.tilt[indices, :, j], dtype='<f4', order='C').tobytes()
                entry['tilt'][field] = asset(f'data/{label}-{corner}-{field}.f32.gz', raw)
            groups[label]['corners'][corner] = entry
        ids = select(data, {'campaign': [label]})
        for field in FIELDS:
            groups[label]['overviews'][field] = {}
            for mode in ('all-recorded', 'evaluation-only'):
                q = quantiles(data, ids, mode, field)
                overview = {}
                for corner, b in q.items():
                    ordered = [b['bands'][100.][0], b['bands'][99.7][0], b['bands'][95.5][0], b['bands'][68.3][0],
                               b['median'], b['bands'][68.3][1], b['bands'][95.5][1], b['bands'][99.7][1], b['bands'][100.][1]]
                    overview[corner] = {'selected': b['selected'], 'count': b['count'].tolist(),
                                        'evaluation_count': b['evaluation_count'].tolist(), 'q': [x.tolist() for x in ordered],
                                        'passed': sum(data.cases[i]['screening_passed'] for i in b['ids'])}
                groups[label]['overviews'][field][mode] = asset(f'data/{label}-{field}-{mode}-overview.json.gz', encode(overview))
        print('Exported', label, flush=True)
    manifest = {'schema_version': 1, 'id': 'isaac-campaigns-20261024-v1', 'case_count': len(data.cases),
                'source_cache_sha256': sha((dataset / 'checksums.json').read_bytes()),
                'case_categories': {'status': sorted({row['status'] for row in data.cases}), 'gpu_index': sorted({row['gpu_index'] for row in data.cases})},
                'time_s': data.time.tolist(), 'fields': FIELDS, 'groups': groups,
                'numeric_format': 'Lossless little-endian IEEE float32, case-major then time; original audited cache values.',
                'quantile_method': 'Pointwise linear sample quantiles, probabilities 0,.0015,.0225,.1585,.5,.8415,.9775,.9985,1.',
                'scope': 'Public projection: tilt trajectories, selected case factors, resolved model/controller and screening settings. Full raw campaign archives remain private.'}
    content = encode(manifest)
    # Fail visibly if an unexpected input field introduces a local path or private infrastructure identifier.
    for token in (b'/home/', b'/Users/', b'gpu_uuid', b'127.0.0.1', b'api_key', b'access_token'):
        if token in content:
            raise ValueError('Private/local field in publication manifest: ' + token.decode())
    if re.search(rb'GPU-[0-9a-fA-F]{8}-', content):
        raise ValueError('Infrastructure GPU identifier in publication manifest')
    (output / 'data/manifest.json').write_bytes(content)
    page = report.read_text()
    if '/home/' in page or '/Users/' in page:
        raise ValueError('Report contains a local host path')
    page = page.replace('<a href="#">One-Piece / Engineering Agents</a>', '<a href="/en/">One-Piece / Engineering Agents</a><a href="/isaac/viewer/">Filterable campaign viewer</a>')
    (output / 'report/index.html').write_text(page)
    receipt = {'schema_version': 1, 'scope': manifest['scope'], 'source_cache_sha256': manifest['source_cache_sha256'],
               'source_report_sha256': sha(report.read_bytes()), 'published_report_sha256': sha(page.encode()),
               'trajectories': len(data.cases), 'samples_per_trajectory': len(data.time), 'fields': FIELDS,
               'manifest_sha256': sha(content), 'compressed_files': files}
    (output / 'publication.json').write_bytes(encode(receipt))
    print('Web export:', output, sum(p.stat().st_size for p in output.rglob('*') if p.is_file()), 'bytes', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis-source', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.analysis_source.resolve()))
    export(args.dataset, args.report, args.output)
