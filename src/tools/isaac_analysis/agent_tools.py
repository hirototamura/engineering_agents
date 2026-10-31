"""Small read-only tool surface for Engineering Agents and other orchestrators.

Construct with an audited dataset. Tools cannot select arbitrary host paths,
change physics, run a model or decide requirements. Full-resolution exports use
the CLI; model-facing responses have explicit size bounds and case denominators.
"""
from .data import load
from .statistics import select,quantiles,quantile_records,summarize,paired_outcomes

TOOL_SCHEMAS = [
    {'name':'isaac_inventory','description':'Read recorded campaign factors, exact gains and dataset coverage.',
     'parameters':{'type':'object','properties':{},'additionalProperties':False}},
    {'name':'isaac_select','description':'Select recorded cases with JSON filters and report all eight corner denominators.',
     'parameters':{'type':'object','properties':{'where':{'type':'object'},'limit':{'type':'integer','minimum':0,'maximum':100}},'additionalProperties':False}},
    {'name':'isaac_tilt_quantiles','description':'Empirical tilt coverage from every selected case. Explicit post-stop policy; at most 32 time indices.',
     'parameters':{'type':'object','properties':{'where':{'type':'object'},'mode':{'enum':['all-recorded','evaluation-only']},
        'metric':{'enum':['tilt_total_deg','tilt_x_deg','tilt_y_deg']},'time_indices':{'type':'array','items':{'type':'integer'},'maxItems':32}},'required':['mode'],'additionalProperties':False}},
    {'name':'isaac_paired_outcomes','description':'Paired screening outcome differences, exact McNemar tests and Holm adjustment; requires matching plan hashes.',
     'parameters':{'type':'object','properties':{'reference':{'type':'string'},'candidate':{'type':'string'}},'required':['reference','candidate'],'additionalProperties':False}},
]


class IsaacAnalysisTools:
    def __init__(self,dataset):self.dataset=load(dataset,verify=True)

    def call(self,name,arguments):
        schemas={s['name']:s for s in TOOL_SCHEMAS}
        if name not in schemas:raise ValueError('Unknown analysis tool')
        spec=schemas[name]['parameters']
        if set(arguments)-set(spec['properties']) or set(spec.get('required',[]))-set(arguments):raise ValueError('Invalid tool arguments')
        d=self.dataset
        if name=='isaac_inventory':
            return {'case_count':len(d.cases),'time_samples':len(d.time),'campaigns':{k:{'factors':g['factors'],
                'controller':g['payload']['compiled']['controller'],'trial_count':g['trial_count']} for k,g in d.catalog['groups'].items()},
                'scope':'Recorded exploration; no delay/gain sweep or physical acceptance.'}
        if name=='isaac_paired_outcomes':return paired_outcomes(d,arguments['reference'],arguments['candidate'])
        ids=select(d,arguments.get('where',{}))
        if name=='isaac_select':
            limit=arguments.get('limit',20)
            if type(limit) is not int or not 0<=limit<=100:raise ValueError('Case preview limit must be 0–100')
            return {'selected_count':len(ids),'corner_summaries':summarize(d,ids),
                'case_preview':[{'campaign':d.cases[i]['campaign'],'id':d.cases[i]['id'],'index':int(i)} for i in ids[:limit]],
                'preview_is_complete':len(ids)<=limit}
        indices=arguments.get('time_indices',[0,len(d.time)//6,len(d.time)//2,len(d.time)-1])
        if not isinstance(indices,list) or len(indices)>32 or any(type(i) is not int or not 0<=i<len(d.time) for i in indices):raise ValueError('Invalid time indices')
        metric=arguments.get('metric','tilt_total_deg');mode=arguments['mode'];wanted=set(indices)
        records=quantile_records(d,quantiles(d,ids,mode,metric),'filtered-selection',mode,metric)
        records=[r for i,r in enumerate(records) if i%len(d.time) in wanted]
        return {'selected_count':len(ids),'records':records,'coverages_are':'pointwise empirical state percentiles, not confidence intervals',
            'post_stop_policy':mode,'pooled_campaigns':sorted({d.cases[i]['campaign'] for i in ids})}
