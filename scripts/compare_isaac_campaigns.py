"""Compare paired initial conditions without discarding failed trials."""
import argparse
import json
from pathlib import Path
from scipy.stats import binomtest

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('reference',type=Path);parser.add_argument('candidate',type=Path);parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
a=json.loads((args.reference/'plan.json').read_text());b=json.loads((args.candidate/'plan.json').read_text())
if a!=b: raise ValueError('Paired comparison requires the identical frozen trial plan')
first=json.loads((args.reference/'screened-trials.json').read_text());second=json.loads((args.candidate/'screened-trials.json').read_text())
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
with args.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
print(json.dumps(result,indent=2))
