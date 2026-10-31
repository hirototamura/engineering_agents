"""Deterministic screening and descriptive statistics for a complete Isaac campaign."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
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
                or result['source_sha256']!=manifest['source_hashes'][manifest.get('worker_source_key', 'run_cube_batch_isaac.py')]
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



def compare(reference, candidate):
    from scipy.stats import binomtest
    a=json.loads((reference/'plan.json').read_text());b=json.loads((candidate/'plan.json').read_text())
    if a!=b: raise ValueError('Paired comparison requires the identical frozen trial plan')
    first=json.loads((reference/'screened-trials.json').read_text());second=json.loads((candidate/'screened-trials.json').read_text())
    left={r['id']:r for r in first};right={r['id']:r for r in second}
    expected={c['id'] for c in a['cases']}
    if len(left)!=len(first) or len(right)!=len(second) or set(left)!=expected or set(right)!=expected:
        raise ValueError('Missing or duplicate paired trials')
    out={}
    for corner in sorted({r['corner'] for r in first}):
        pairs=[(r,right[k]) for k,r in left.items() if r['corner']==corner]
        improved=sum(not x['screening_passed'] and y['screening_passed'] for x,y in pairs)
        regressed=sum(x['screening_passed'] and not y['screening_passed'] for x,y in pairs)
        n=len(pairs);p=sum(x['screening_passed'] for x,y in pairs)/n;q=sum(y['screening_passed'] for x,y in pairs)/n
        out[corner]={'count':n,'reference_pass_fraction':p,'candidate_pass_fraction':q,'difference_percentage_points':100*(q-p),
            'failed_to_pass':improved,'pass_to_failed':regressed,
            'mcnemar_exact_two_sided_p':float(binomtest(improved,improved+regressed,.5).pvalue) if improved+regressed else 1.,
            'hypothesis_above_95_percent_observed':q>.95}
    result={'corners':out,'physical_verified':False,'cross_backend_agreement':'inconclusive',
        'scope':'Paired exploration, same initial conditions/noise and saved controller. Candidate selection used these exploration results.',
        'statistical_limits':'Eight descriptive comparisons; p-values are unadjusted and do not establish hardware or model fidelity. Fresh validation seeds are needed before selection claims.'}
    return result

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign', type=Path)
    parser.add_argument('--reference', type=Path, help='Compare this candidate with a paired reference campaign')
    parser.add_argument('--output', type=Path, help='Required for paired comparison; new JSON output file')
    args = parser.parse_args(argv)
    if args.reference:
        if args.output is None:
            parser.error('--reference requires --output')
        result = compare(args.reference, args.campaign)
        with args.output.open('x') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
    else:
        if args.output is not None:
            parser.error('--output is only used with --reference')
        result, rows = summarize(args.campaign)
        for name, value in [('statistics.json', result), ('screened-trials.json', rows)]:
            with (args.campaign/name).open('x') as stream:
                json.dump(value, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
