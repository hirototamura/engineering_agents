"""Deterministic screening and descriptive statistics for a complete Isaac campaign."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from scenario.balancing_cube.evaluation import screening


def wilson(successes, total):
    z=1.959963984540054; p=successes/total; denominator=1+z*z/total
    center=(p+z*z/(2*total))/denominator
    half=z*np.sqrt(p*(1-p)/total+z*z/(4*total*total))/denominator
    return [float(center-half),float(center+half)]


def summarize(root):
    manifest=json.loads((root/'manifest.json').read_text())
    if manifest['status']!='completed': raise ValueError('Incomplete campaign')
    plan=json.loads((root/'plan.json').read_text())
    if hashlib.sha256((root/'plan.json').read_bytes()).hexdigest()!=manifest['plan_sha256']:
        raise ValueError('Trial plan changed')
    payload_path=Path(manifest['input'])/'input.json'
    if hashlib.sha256(payload_path.read_bytes()).hexdigest()!=manifest['input_sha256']:
        raise ValueError('Source design changed')
    payload=json.loads(payload_path.read_text()); contract=payload['snapshot']['contract']
    for relative,expected_hash in manifest.get('asset_hashes',{}).items():
        if hashlib.sha256((payload_path.parent/relative).read_bytes()).hexdigest()!=expected_hash:
            raise ValueError('Converted USD asset changed')
    expected={c['id']:c for c in plan['cases']}; seen=set(); rows=[]; evidence=[]
    for shard in manifest['shards']:
        path=root/f"shard-{shard['rank']}"/'result.json'
        result=json.loads(path.read_text())
        if (result['gpu_uuid']!=shard['gpu_uuid'] or result['cases_sha256']!=shard['cases_sha256']
                or result['input_digest']!=payload['compiled']['input_digest']
                or result['source_sha256']!=manifest['source_hashes']['run_cube_batch_isaac.py']
                or result['trial_count']!=shard['trial_count']
                or len(result['summaries'])!=shard['trial_count']):
            raise ValueError('Shard provenance or count mismatch')
        for row in result['summaries']:
            if row['id'] in seen or row['id'] not in expected: raise ValueError('Duplicate or unknown trial')
            if any(row.get(k)!=v for k,v in expected[row['id']].items()): raise ValueError('Trial inputs changed')
            seen.add(row['id']); checks=screening(row,contract)
            rows.append({**row,'screening_passed':all(c['passed'] for c in checks),
                         'failed_metrics':[c['metric'] for c in checks if not c['passed']]})
        evidence.append({'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    if seen!=set(expected): raise ValueError('Missing trials cannot be excluded from statistics')
    corners={}
    for corner in sorted({r['corner'] for r in rows}):
        group=[r for r in rows if r['corner']==corner]; passed=sum(r['screening_passed'] for r in group)
        corners[corner]={'count':len(group),'screening_pass_count':passed,'screening_pass_fraction':passed/len(group),
            'wilson_95_ci':wilson(passed,len(group)),'status_counts':dict(Counter(r['status'] for r in group)),
            'failed_metric_counts':dict(Counter(m for r in group for m in r['failed_metrics'])),
            'quantiles':{key:dict(zip(['p05','p50','p95','max'],np.quantile([r[key] for r in group],[.05,.5,.95,1]).tolist()))
                for key in ['peak_tilt_deg','final_1s_tilt_rms_deg','peak_wheel_rpm','peak_slip_speed_m_s','peak_pivot_displacement_mm']}}
    return {'trial_count':len(rows),'corners':corners,'evidence':evidence,'plan_sha256':manifest['plan_sha256'],
        'input_digest':payload['compiled']['input_digest'],'criteria':contract['screening'],
        'physical_verified':False,'cross_backend_agreement':'not established by this campaign',
        'scope':'Exploratory eight-corner extension. Existing numerical gates are reused; no adopted baseline or requirement change.',
        'uncertainty':'Wilson intervals describe this seeded initial-condition distribution, not model or hardware uncertainty.'},rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('campaign',type=Path);args=parser.parse_args()
    stats,rows=summarize(args.campaign)
    for name,value in [('statistics.json',stats),('screened-trials.json',rows)]:
        with (args.campaign/name).open('x') as f: json.dump(value,f,indent=2,allow_nan=False)
    print(json.dumps(stats,indent=2))
