"""Analysis must keep failures, denominators, and filters reproducible."""
import json
from pathlib import Path
import numpy as np
import pytest
from tools.isaac_analysis.data import Dataset,prepare,sha256,load
from tools.isaac_analysis.statistics import select,quantiles,quantile_records,paired_outcomes
from tools.isaac_analysis.figures import plot_bands,tilt_zoom_domain
from tools.isaac_analysis.report import protocol_groups
from tools.isaac_analysis.agent_tools import IsaacAnalysisTools


@pytest.fixture
def dataset(tmp_path):
    rows=[]
    for label in ('reference','candidate'):
        for j in range(2):
            rows.append({'index':len(rows),'campaign':label,'id':str(j),'corner':'000',
                'end_tick':2 if j==0 else 0,'status':'completed' if j==0 else 'lost_balance',
                'initial_tilt_radius_deg':float(j),'initial_yaw_rate_rad_s':-.5 if j==0 else .5,
                'seed':j+10,'gpu_index':j,'failed_metrics':[],'screening_passed':j==0 if label=='reference' else False})
    values=np.zeros((4,3,3));values[0,:,2]=[0,1,2];values[1,:,2]=[0,100,200];values[2:]=values[:2]
    groups={label:{'factors':{'side_m':.16 if label=='reference' else .18,'observation_delay_s':.015},
        'manifest':{'plan_sha256':'same'}} for label in ('reference','candidate')}
    return Dataset(tmp_path,{'groups':groups},rows,values,np.array([0,.015,.03]))


def test_all_recorded_includes_failed_free_evolution(dataset):
    ids=select(dataset,{'campaign':['reference']});q=quantiles(dataset,ids)['000']
    np.testing.assert_array_equal(q['count'],[2,2,2]);np.testing.assert_array_equal(q['evaluation_count'],[2,1,1])
    assert q['median'][-1]==101
    assert q['bands'][100.][1][-1]==200
    assert q['bands'][68.3][0][-1]==pytest.approx(np.quantile([2,200],.1585))


def test_evaluation_stop_is_inclusive_and_no_carry_forward(dataset):
    q=quantiles(dataset,select(dataset,{'campaign':['reference']}),'evaluation-only')['000']
    np.testing.assert_array_equal(q['count'],[2,1,1]);assert q['median'][-1]==2
    empty=quantiles(dataset,[],mode='evaluation-only')
    assert len(empty)==8 and all(b['selected']==0 for b in empty.values())
    records=quantile_records(dataset,empty,'none','evaluation-only','tilt_total_deg')
    assert records[0]['median'] is None
    json.dumps(records,allow_nan=False)


def test_different_mechanical_populations_are_not_silently_pooled(dataset):
    with pytest.raises(ValueError,match='one campaign'):quantiles(dataset,select(dataset))
    with pytest.raises(ValueError,match='Duplicate'):quantiles(dataset,[0,0])


def test_factor_and_case_filters_are_joint_and_inclusive(dataset):
    assert select(dataset,{'side_m':[.18,.18],'observation_delay_s':[.015,.015],
        'initial_tilt_radius_deg':[1,1],'seed_values':[11],'gpu_indices':[1]}).tolist()==[3]
    assert select(dataset,{'campaign':[]}).tolist()==[]


@pytest.mark.parametrize('where',[{'missing':[0,1]},{'side_m':[.2,.1]},{'side_m':[0,float('nan')]},{'side_m':'bad'}])
def test_invalid_filters_fail_visibly(dataset,where):
    with pytest.raises(ValueError):select(dataset,where)


def test_shared_figure_limits_do_not_clip_failures(dataset):
    import matplotlib.pyplot as plt
    dataset.cases[1]['corner']='111'  # large values in the last shared axis
    fig,_=plot_bands(dataset,select(dataset,{'campaign':['reference']}))
    assert fig.axes[0].get_ylim()[1]>=200
    plt.close(fig)


def test_paired_regression_and_unpaired_plan_rejection(dataset):
    q=paired_outcomes(dataset,'reference','candidate')
    assert q[0]['pass_to_fail']==1 and q[0]['fail_to_pass']==0
    dataset.catalog['groups']['candidate']['manifest']['plan_sha256']='different'
    with pytest.raises(ValueError):paired_outcomes(dataset,'reference','candidate')


def test_report_roles_follow_pinned_inputs_not_insertion_order_or_labels(dataset,tmp_path):
    from tools.isaac_analysis.statistics import summarize
    from tools.isaac_analysis.presentation import render_report
    digests={'reference':'151f2bd27d18139b73b5b26f6cdcfff7926c534922e2971bd57ab3b4608483a8',
             'candidate':'b4b65a32da74137d5b91666e7d2ab383ac27c66bf38cc74d8106493f26be7227'}
    # Arbitrary CLI labels deliberately sort in the opposite role order.
    names={'reference':'z-baseline','candidate':'a-proposal'}
    for label,group in dataset.catalog['groups'].items():
        group['payload']={'compiled':{'input_digest':digests[label]}}
        group['manifest']['plan_sha256']='97776e29c25b46dbbca6595c5b7563b54f431d4d99493a7c0b5c32cda777250f'
        group['factors']['total_mass_kg']=.7
    dataset.catalog['groups']={names[k]:dataset.catalog['groups'][k] for k in ('candidate','reference')}
    for row in dataset.cases:row['campaign']=names[row['campaign']]
    groups=protocol_groups(dataset)
    assert list(groups)==['z-baseline','a-proposal']
    paired=paired_outcomes(dataset,*groups)
    assert paired[0]['pass_to_fail']==1 and paired[0]['fail_to_pass']==0
    assert paired[0]['difference_pp']==-50
    markdown='\n'.join(f'## {i}. Section\nEvidence\n' for i in range(1,13))
    summary=[r for r in summarize(dataset,select(dataset)) if r['cases']]
    render_report(markdown,tmp_path,summary,paired,groups)
    html=(tmp_path/'technical-report.html').read_text()
    assert '<div class="result reference"><h3>Z-baseline</h3>' in html
    assert '<div class="result candidate"><h3>A-proposal</h3>' in html
    assert '1 paired cases changed from pass to fail; 0 changed from fail to pass' in html
    dataset.catalog['groups']['a-proposal']['payload']['compiled']['input_digest']='other'
    with pytest.raises(ValueError,match='frozen architectures'):protocol_groups(dataset)


@pytest.mark.parametrize('metric',['tilt_x_deg','tilt_y_deg','tilt_total_deg'])
@pytest.mark.parametrize('upper',[5,.5])
def test_zoom_domains_keep_signed_tilt_visible(metric,upper):
    low,high=tilt_zoom_domain(metric,upper)
    assert high==upper
    assert low==(0 if metric=='tilt_total_deg' else -upper)
    if metric!='tilt_total_deg':assert low < -.1 < .1 < high


def test_agent_tools_are_bounded_and_keep_denominators(dataset):
    tools=IsaacAnalysisTools.__new__(IsaacAnalysisTools);tools.dataset=dataset
    result=tools.call('isaac_select',{'where':{'campaign':['reference']},'limit':1})
    assert result['selected_count']==2 and len(result['case_preview'])==1 and not result['preview_is_complete']
    result=tools.call('isaac_tilt_quantiles',{'where':{'campaign':['reference']},'mode':'all-recorded','time_indices':[2]})
    assert len(result['records'])==8 and result['records'][0]['count']==2
    with pytest.raises(ValueError):tools.call('isaac_select',{'limit':101})
    with pytest.raises(ValueError):tools.call('isaac_select',{'path':'/arbitrary'})
    with pytest.raises(ValueError):tools.call('isaac_tilt_quantiles',{'mode':'all-recorded','time_indices':list(range(33))})


def original_campaign(tmp_path, worker_source_key=None):
    root=tmp_path/'campaign';root.mkdir();inp=tmp_path/'input';inp.mkdir();shard=root/'shard-0';shard.mkdir()
    p={'cube_side_m':.16,'frame_mass_kg':.5,'frame_com_fraction':[.5]*3,'frame_inertia_kg_m2':[.002]*3,
        'wheel_mass_kg':.05,'wheel_radius_m':.04,'wheel_axial_inertia_kg_m2':.0001,'wheel_thickness_m':.006,
        'wheel_face_inset_m':.012,'wheel_mount_side':'near_corner_000','control_period_s':.015,'timestep_s':.001}
    payload={'compiled':{'config':{'physics':p,'sensing':{}},'controller':{'yaw_rate_gain_nm_s':.03},'input_digest':'fixed'},
        'snapshot':{'contract':{'screening':{'criteria':[{'metric':'peak_tilt_deg','operator':'<=','limit':5}], 'required_duration_s':.03}}}}
    (inp/'input.json').write_text(json.dumps(payload))
    case={'id':'one','corner':'000','initial_tilt_deg':[0.,0.],'initial_yaw_rate_rad_s':0.,'seed':10,'duration_s':.03}
    (root/'plan.json').write_text(json.dumps({'seed':1,'cases':[case],'trial_count':1}))
    (root/'cases-0.json').write_text(json.dumps({'cases':[case]}))
    worker=worker_source_key or 'run_cube_batch_isaac.py'
    (root/'sources').mkdir();code=root/'sources'/worker;code.write_text('# frozen source')
    manifest={'status':'completed','input':str(inp),'input_sha256':sha256(inp/'input.json'),'plan_sha256':sha256(root/'plan.json'),
        'source_hashes':{worker:sha256(code)},'shards':[{'rank':0,'gpu_uuid':'gpu','gpu_index':0,'trial_count':1,'cases_sha256':sha256(root/'cases-0.json')}]}
    if worker_source_key is not None:manifest['worker_source_key']=worker_source_key
    (root/'manifest.json').write_text(json.dumps(manifest))
    result={'gpu_uuid':'gpu','input_digest':'fixed','source_sha256':sha256(code),'trial_count':1,'cases_sha256':sha256(root/'cases-0.json'),
        'summaries':[{**case,'peak_tilt_deg':2.,'status':'completed','simulated_duration_s':.03}]}
    (shard/'result.json').write_text(json.dumps(result))
    raw=np.zeros((3,1,3));raw[:,0,2]=[0,1,2]
    np.savez(shard/'telemetry.npz',values=raw,time_s=np.array([0,.015,.03]),fields=['tilt_x_deg','tilt_y_deg','tilt_total_deg'],end_tick=np.array([2]),status=np.array([0]))
    return root


@pytest.mark.parametrize('worker_source_key',[None,'batch.py'])
def test_preparation_and_hash_verification(tmp_path,worker_source_key):
    root=original_campaign(tmp_path,worker_source_key);out=tmp_path/'derived';d=prepare({'tiny':root},out)
    assert len(d.cases)==1 and d.tilt[0,-1,2]==2
    with (out/'tilt.npy').open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='cache changed'):load(out,verify=True)


@pytest.mark.parametrize('worker_source_key',[None,'batch.py'])
def test_preparation_rejects_wrong_worker_hash(tmp_path,worker_source_key):
    root=original_campaign(tmp_path,worker_source_key);path=root/'shard-0/result.json'
    result=json.loads(path.read_text());result['source_sha256']='wrong-worker-hash'
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError,match='Shard provenance mismatch'):prepare({'bad':root},tmp_path/'bad-derived')


def test_preparation_rejects_conflicting_raw_summary(tmp_path):
    root=original_campaign(tmp_path);path=root/'shard-0/result.json';r=json.loads(path.read_text());r['summaries'][0]['peak_tilt_deg']=1
    path.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='Peak tilt'):prepare({'bad':root},tmp_path/'bad-derived')
