"""Validate archived campaigns and build an immutable analysis cache.

The cache is derived evidence. It never changes simulator inputs or historical
measurements. Original manifests did not hash telemetry; this reader records
its hashes and checks its contents against the independently recorded summaries.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import numpy as np
from scenario.balancing_cube.evaluation import screening

CORNERS = tuple(f'{i:03b}' for i in range(8))
STATUS = ('completed', 'lost_balance', 'lost_contact', 'excessive_slip', 'numerical_failure')
TILT_FIELDS = ('tilt_x_deg', 'tilt_y_deg', 'tilt_total_deg')


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8*1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    with Path(path).open('x') as f: json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)


def factors(payload):
    c = payload['compiled']; p = c['config']['physics']; s = c['config'].get('sensing', {})
    side = p['cube_side_m']; mass = p['frame_mass_kg']+3*p['wheel_mass_kg']
    centers = np.full((3, 3), side/2)
    np.fill_diagonal(centers, p['wheel_face_inset_m'] if p['wheel_mount_side']=='near_corner_000' else side-p['wheel_face_inset_m'])
    com = (np.array(p['frame_com_fraction'])*side*p['frame_mass_kg']+centers.sum(0)*p['wheel_mass_kg'])/mass
    return {'side_m':side, 'total_mass_kg':mass, 'frame_mass_kg':p['frame_mass_kg'],
        'wheel_mass_kg':p['wheel_mass_kg'], 'wheel_radius_m':p['wheel_radius_m'],
        'wheel_axial_inertia_kg_m2':p['wheel_axial_inertia_kg_m2'],
        'frame_inertia_kg_m2':p['frame_inertia_kg_m2'][0],
        'wheel_thickness_m':p['wheel_thickness_m'], 'observation_delay_s':s.get('control_delay_s',0),
        'control_period_s':p['control_period_s'], 'timestep_s':p['timestep_s'],
        'tilt_noise_std_deg':s.get('tilt_noise_std_deg',0), 'gyro_noise_std_deg_s':s.get('gyro_noise_std_deg_s',0),
        'yaw_gain_nm_s':c['controller']['yaw_rate_gain_nm_s'], 'controller_digest':digest(c['controller']),
        'wheel_mount_side':p['wheel_mount_side'], 'body_com_m':com.tolist(), 'wheel_centers_body_m':centers.tolist()}


def inspect_campaign(root):
    root = Path(root).resolve(); m = json.loads((root/'manifest.json').read_text())
    if m.get('status') != 'completed': raise ValueError('Incomplete campaign: '+str(root))
    if sha256(root/'plan.json') != m['plan_sha256']: raise ValueError('Plan hash mismatch')
    ppath = Path(m['input'])/'input.json'
    # Relocated evidence: use a sibling input directory, without editing receipts.
    if not ppath.exists(): ppath = root.parent/Path(m['input']).name/'input.json'
    if sha256(ppath) != m['input_sha256']: raise ValueError('Input hash mismatch')
    payload = json.loads(ppath.read_text()); plan = json.loads((root/'plan.json').read_text())
    cases = plan['cases']; expected = {c['id']:c for c in cases}
    if len(expected)!=len(cases) or plan['trial_count']!=len(cases): raise ValueError('Duplicate or missing planned cases')
    return root, m, payload, plan


def prepare(campaigns, output):
    """campaigns maps unique analyst labels to original campaign directories."""
    if not campaigns: raise ValueError('At least one campaign is required')
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',label) for label in campaigns):
        raise ValueError('Campaign labels must be short ASCII names without path separators')
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    specs = {label:inspect_campaign(path) for label,path in campaigns.items()}
    total = sum(len(s[3]['cases']) for s in specs.values())
    rows = []; groups = {}; evidence = []; reference_time = None; values = None
    for label,(root,m,payload,plan) in specs.items():
        group_factors = factors(payload); expected = {c['id']:c for c in plan['cases']}; seen = set()
        groups[label] = {'campaign_path':str(root),'manifest':m,'plan_distribution':plan.get('distribution'),
            'plan_seed':plan['seed'],'payload':payload,'factors':group_factors,'trial_count':len(expected)}
        for name,expected_hash in m['source_hashes'].items():
            path=root/'sources'/name
            if not path.is_file() or sha256(path)!=expected_hash: raise ValueError('Archived source copy missing or changed: '+name)
            evidence.append({'path':str(path),'sha256':expected_hash})
        for path in [root/'manifest.json', root/'plan.json', Path(m['input'])/'input.json']:
            if path.exists(): evidence.append({'path':str(path),'sha256':sha256(path)})
        for shard in m['shards']:
            rank = shard['rank']; folder = root/f'shard-{rank}'
            result_path = folder/'result.json'; result = json.loads(result_path.read_text())
            case_path = root/f'cases-{rank}.json'
            if sha256(case_path)!=shard['cases_sha256']: raise ValueError('Shard cases hash mismatch')
            if (result['input_digest']!=payload['compiled']['input_digest'] or result['gpu_uuid']!=shard['gpu_uuid']
                    or result['cases_sha256']!=shard['cases_sha256']
                    or result['source_sha256']!=m['source_hashes'][m.get('worker_source_key','run_cube_batch_isaac.py')]
                    or result['trial_count']!=shard['trial_count']): raise ValueError('Shard provenance mismatch')
            for file in [result_path, folder/'telemetry.npz', case_path]:
                evidence.append({'path':str(file),'sha256':sha256(file)})
            with np.load(folder/'telemetry.npz', allow_pickle=False) as archive:
                raw = archive['values']; time = archive['time_s']; ends = archive['end_tick']; statuses = archive['status']
                fields = archive['fields'].tolist(); summaries = result['summaries']; n = len(summaries)
                if [c['id'] for c in json.loads(case_path.read_text())['cases']]!=[s['id'] for s in summaries]:
                    raise ValueError('Shard case order changed')
                if raw.shape!=(len(time),n,len(fields)) or n!=shard['trial_count']: raise ValueError('Telemetry dimensions disagree')
                if not np.isfinite(raw).all() or not np.isfinite(time).all() or not np.all(np.diff(time)>0):
                    raise ValueError('Invalid or nonfinite telemetry')
                if ends.shape!=(n,) or statuses.shape!=(n,) or not np.issubdtype(ends.dtype,np.integer): raise ValueError('Invalid stopping indices')
                if np.any(ends<0) or np.any(ends>=len(time)) or np.any(statuses<0) or np.any(statuses>=len(STATUS)): raise ValueError('Invalid stop/status code')
                if not np.allclose(np.diff(time),payload['compiled']['config']['physics']['control_period_s'],rtol=0,atol=1e-10): raise ValueError('Unexpected time grid')
                if reference_time is None:
                    reference_time = time.copy(); np.save(output/'time_s.npy',reference_time)
                    values = np.lib.format.open_memmap(output/'tilt.npy',mode='w+',dtype=np.float32,shape=(total,len(time),3))
                elif not np.array_equal(time,reference_time): raise ValueError('Campaign time grids differ; resampling must be explicit')
                tilt = raw[:,:,[fields.index(k) for k in TILT_FIELDS]]
                for j,summary in enumerate(summaries):
                    key = summary['id']
                    if key in seen or key not in expected: raise ValueError('Duplicate or unknown case')
                    if any(summary.get(k)!=v for k,v in expected[key].items()): raise ValueError('Changed initial condition')
                    seen.add(key); end = int(ends[j]); status = STATUS[int(statuses[j])]
                    if status!=summary['status'] or not np.isclose(time[end],summary['simulated_duration_s'],atol=1e-8): raise ValueError('Termination metadata disagree')
                    if not np.isclose(tilt[:end+1,j,2].max(),summary['peak_tilt_deg'],rtol=1e-6,atol=1e-6): raise ValueError('Peak tilt summary differs from raw data')
                    if status=='completed' and end!=len(time)-1: raise ValueError('Completed case has truncated data')
                    initial = expected[key]; xy = initial['initial_tilt_deg']; radius = float(np.linalg.norm(xy))
                    # acos(float32 direction_z) is quantized near upright. Its
                    # smallest nonzero angle is ~0.02 degrees; use a declared
                    # 0.06-degree consistency tolerance, not an acceptance gate.
                    if not np.isclose(tilt[0,j,2],radius,atol=.06): raise ValueError('Initial tilt does not match plan')
                    checks = screening(summary,payload['snapshot']['contract'])
                    row = {**summary, 'index':len(rows),'campaign':label,'gpu_index':shard['gpu_index'],
                        'gpu_uuid':shard['gpu_uuid'],'shard_rank':rank,'local_index':j,'end_tick':end,
                        'initial_tilt_x_deg':xy[0],'initial_tilt_y_deg':xy[1],'initial_tilt_radius_deg':radius,
                        'initial_tilt_azimuth_deg':float(np.rad2deg(np.arctan2(xy[1],xy[0]))),
                        'screening_passed':all(c['passed'] for c in checks),'failed_metrics':[c['metric'] for c in checks if not c['passed']]}
                    values[len(rows)] = tilt[:,j,:]; rows.append(row)
        if seen!=set(expected): raise ValueError('Missing trials')
    values.flush(); del values
    write_json(output/'cases.json',rows)
    write_json(output/'catalog.json',{'schema_version':1,'groups':groups,'case_count':len(rows),
        'tilt_fields':TILT_FIELDS,'evidence':evidence,'time_samples':len(reference_time),
        'post_stop_policy':'Raw pose-derived tilt continues after stop with zero commanded effort. These are not controlled evaluations.',
        'torque_caveat':'Archived motor_* telemetry after stopping is the computed hypothetical limited request, not the zero effort actually sent. No post-stop torque inference is supported.'})
    write_json(output/'checksums.json',{p.name:sha256(p) for p in output.iterdir() if p.is_file()})
    return load(output)


class Dataset:
    def __init__(self, root, catalog, cases, tilt, time):
        self.root,self.catalog,self.cases,self.tilt,self.time = root,catalog,cases,tilt,time

    def factor(self, case, key):
        key={'gpu_indices':'gpu_index','seed_values':'seed'}.get(key,key)
        if key in case: return case[key]
        return self.catalog['groups'][case['campaign']]['factors'].get(key)


def load(root, verify=False):
    root=Path(root)
    if verify:
        for name,expected in json.loads((root/'checksums.json').read_text()).items():
            if sha256(root/name)!=expected: raise ValueError('Analysis cache changed: '+name)
    catalog=json.loads((root/'catalog.json').read_text());cases=json.loads((root/'cases.json').read_text())
    tilt=np.load(root/'tilt.npy',mmap_mode='r',allow_pickle=False);time=np.load(root/'time_s.npy',allow_pickle=False)
    if tilt.shape!=(len(cases),len(time),3) or len(cases)!=catalog['case_count']: raise ValueError('Cache shape mismatch')
    return Dataset(root,catalog,cases,tilt,time)
