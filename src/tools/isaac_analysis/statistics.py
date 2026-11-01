"""Empirical Monte Carlo summaries with explicit denominators and stopping rules."""
from __future__ import annotations

from collections import Counter
import math
import numpy as np
from .data import CORNERS, TILT_FIELDS

COVERAGES = (68.3,95.5,99.7,100.)
NUMERIC_FILTERS = {'initial_tilt_radius_deg','initial_tilt_x_deg','initial_tilt_y_deg',
    'initial_tilt_azimuth_deg','initial_yaw_rate_rad_s','seed','side_m','total_mass_kg','frame_mass_kg',
    'wheel_mass_kg','wheel_radius_m','wheel_axial_inertia_kg_m2','frame_inertia_kg_m2',
    'wheel_thickness_m','observation_delay_s','control_period_s','timestep_s','tilt_noise_std_deg',
    'gyro_noise_std_deg_s','yaw_gain_nm_s','simulated_duration_s','gpu_index'}
CATEGORY_FILTERS = {'campaign','corner','status','screening_passed','controller_digest','wheel_mount_side','id','gpu_uuid','gpu_indices','seed_values'}


def select(dataset, where=None):
    """JSON conditions: numeric [min,max] inclusive; categories use explicit lists."""
    where=where or {}; unknown=set(where)-NUMERIC_FILTERS-CATEGORY_FILTERS
    if unknown: raise ValueError('Unknown filter fields: '+', '.join(sorted(unknown)))
    for key,rule in where.items():
        if not isinstance(rule,list): raise ValueError('Filter values must be lists')
        if key in NUMERIC_FILTERS and (len(rule)!=2 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in rule) or rule[0]>rule[1]):
            raise ValueError('Numeric filters require finite [minimum,maximum]')
    selected=[]
    for row in dataset.cases:
        include=True
        for key,rule in where.items():
            value=dataset.factor(row,key)
            if key in NUMERIC_FILTERS: include=value is not None and rule[0]<=value<=rule[1]
            else: include=value in rule
            if not include: break
        if include: selected.append(row['index'])
    return np.asarray(selected,dtype=np.int64)


def quantiles(dataset, indices, mode='all-recorded', metric='tilt_total_deg'):
    indices=np.asarray(indices)
    if indices.ndim!=1 or (len(indices) and (not np.issubdtype(indices.dtype,np.integer) or np.any(indices<0) or np.any(indices>=len(dataset.cases)))):
        raise ValueError('Invalid case indices')
    if len(np.unique(indices))!=len(indices):raise ValueError('Duplicate cases cannot be weighted twice')
    if mode not in {'all-recorded','evaluation-only'}: raise ValueError('Unknown post-stop policy')
    if metric not in TILT_FIELDS: raise ValueError('Only archived pose-derived tilt is supported here')
    if len({dataset.cases[i]['campaign'] for i in indices})>1:
        raise ValueError('Select one campaign for quantiles; plot distinct mechanical populations separately')
    field=TILT_FIELDS.index(metric); ticks=np.arange(len(dataset.time)); result={}
    for corner in CORNERS:
        ids=np.asarray([int(i) for i in indices if dataset.cases[i]['corner']==corner],dtype=int)
        if len(ids):
            values=np.array(dataset.tilt[ids,:,field],dtype=np.float64)
            ends=np.asarray([dataset.cases[i]['end_tick'] for i in ids])
            valid=ticks[None,:]<=ends[:,None]
            if mode=='evaluation-only': values[~valid]=np.nan
            count=np.isfinite(values).sum(0)
            qs=np.full((9,len(ticks)),np.nan)
            present=count>0
            # Do not use padding, carry-forward or interpolation after stopping.
            if np.any(present):qs[:,present]=np.nanquantile(values[:,present],[0,.0015,.0225,.1585,.5,.8415,.9775,.9985,1],axis=0,method='linear')
            result[corner]={'selected':len(ids),'count':count,'evaluation_count':valid.sum(0),
                'median':qs[4],'bands':{coverage:(qs[k],qs[8-k]) for k,coverage in enumerate((100.,99.7,95.5,68.3))},
                'ids':ids}
        else:
            empty=np.full(len(ticks),np.nan)
            result[corner]={'selected':0,'count':np.zeros(len(ticks),int),'evaluation_count':np.zeros(len(ticks),int),
                'median':empty,'bands':{c:(empty.copy(),empty.copy()) for c in COVERAGES},'ids':ids}
    return result


def quantile_records(dataset, bands, campaign, mode, metric):
    records=[]
    def finite(value): return float(value) if np.isfinite(value) else None
    for corner,b in bands.items():
        for j,time in enumerate(dataset.time):
            row={'campaign':campaign,'corner':corner,'time_s':float(time),'mode':mode,'metric':metric,
                'selected':b['selected'],'count':int(b['count'][j]),'evaluation_count':int(b['evaluation_count'][j]),
                'median':finite(b['median'][j])}
            for coverage,(lo,hi) in b['bands'].items():
                name=str(coverage).replace('.','_');row['lo_'+name]=finite(lo[j]);row['hi_'+name]=finite(hi[j])
            records.append(row)
    return records


def wilson(passed,n):
    if n==0:return None
    z=1.959963984540054;p=passed/n;den=1+z*z/n
    mid=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0,mid-half),min(1,mid+half)]


def summarize(dataset, indices):
    groups=[]
    for label in dataset.catalog['groups']:
        for corner in CORNERS:
            rows=[dataset.cases[i] for i in indices if dataset.cases[i]['campaign']==label and dataset.cases[i]['corner']==corner]
            n=len(rows);passed=sum(r['screening_passed'] for r in rows)
            groups.append({'campaign':label,'corner':corner,'cases':n,'screening_passed':passed,
                'pass_fraction':passed/n if n else None,'wilson_95':wilson(passed,n),
                'status_counts':dict(Counter(r['status'] for r in rows)),
                'failed_metric_counts':dict(Counter(k for r in rows for k in r['failed_metrics']))})
    return groups


def risk_bins(dataset, indices):
    records=[]
    for label in dataset.catalog['groups']:
        for corner in CORNERS:
            for lo,hi in zip(range(5),range(1,6)):
                rows=[dataset.cases[i] for i in indices if dataset.cases[i]['campaign']==label and dataset.cases[i]['corner']==corner
                    and lo<=dataset.cases[i]['initial_tilt_radius_deg'] and (dataset.cases[i]['initial_tilt_radius_deg']<hi or (hi==5 and dataset.cases[i]['initial_tilt_radius_deg']<=hi))]
                n=len(rows);passed=sum(r['screening_passed'] for r in rows)
                records.append({'campaign':label,'corner':corner,'initial_radius_bin_deg':f'{lo}–{hi}',
                    'count':n,'passed':passed,'pass_fraction':passed/n if n else None,'wilson_95':wilson(passed,n)})
    return records


def paired_outcomes(dataset, first, second):
    a=dataset.catalog['groups'][first];b=dataset.catalog['groups'][second]
    if a['manifest']['plan_sha256']!=b['manifest']['plan_sha256']:raise ValueError('Plans are not paired')
    left={r['id']:r for r in dataset.cases if r['campaign']==first};right={r['id']:r for r in dataset.cases if r['campaign']==second}
    if set(left)!=set(right):raise ValueError('Paired cases are missing')
    out=[]
    for corner in CORNERS:
        pairs=[(r,right[k]) for k,r in left.items() if r['corner']==corner]
        improved=sum(not x['screening_passed'] and y['screening_passed'] for x,y in pairs)
        regressed=sum(x['screening_passed'] and not y['screening_passed'] for x,y in pairs)
        n=len(pairs);d=improved+regressed
        # Exact two-sided binomial McNemar test, dependency-free and stable at the
        # observed (zero-improvement) extreme. No continuity approximation.
        k=min(improved,regressed)
        logs=[math.lgamma(d+1)-math.lgamma(j+1)-math.lgamma(d-j+1)-d*math.log(2) for j in range(k+1)] if d else []
        p=min(1.,2*sum(math.exp(v) for v in logs)) if d else 1.
        out.append({'corner':corner,'pairs':n,'fail_to_pass':improved,'pass_to_fail':regressed,
            'difference_pp':100*(improved-regressed)/n if n else None,'mcnemar_exact_p':p})
    order=sorted(range(len(out)),key=lambda i:out[i]['mcnemar_exact_p']);last=0.
    for rank,i in enumerate(order):
        last=max(last,min(1.,(len(out)-rank)*out[i]['mcnemar_exact_p']));out[i]['holm_adjusted_p']=last
    return out
