"""Contract and data-flow checks assume qualified lower-level calculators."""
import hashlib
import json
from pathlib import Path
import pytest
from environment.engineering_analysis import catalog,control_composition,electrical
from tools.engineering_skills.runner import run

REPO = Path(__file__).resolve().parents[2]


def test_catalog_contracts_are_portable_explicit_and_acyclic():
    catalog.validate_graph()
    for name,skill in catalog.SKILLS.items():
        body = json.loads((REPO/'skills/engineering'/name/'contract.json').read_text())
        assert all(body[k] == v for k,v in skill.contract().items())
        assert bool(skill.requires) == (body['kind']=='composite')
        assert skill.project_specific == (name=='cube-gnc-loop-analysis')
        assert body['primary_output']['file'] == 'result.json'


def test_cycles_are_rejected(monkeypatch):
    monkeypatch.setitem(catalog.SKILLS,'loop',catalog.Skill('loop','example','systems',requires=('loop',)))
    with pytest.raises(ValueError,match='cycle'):catalog.validate_graph()


def test_bode_composition_handoff_and_criterion_logic_without_retesting_math():
    data={'units':'SI','data_basis':'synthetic_validation','omega_rad_s':[1,10],
          'criteria':[{'metric':'magnitude_db','operator':'<=','value':-3,'omega_rad_s':2}]}
    results={};jobs=control_composition.bode_jobs(data,results)
    role,skill,value=next(jobs)
    assert role=='plant' and skill=='transfer-function-derivation' and value is data
    plant={'transfer_function':{'sentinel':'qualified-transfer'},'state_poles_per_s':[{'real':-1,'imag':0}]}
    results['plant']=plant
    role,skill,value=next(jobs)
    assert skill=='frequency-response-calculation' and value['transfer_function'] is plant['transfer_function']
    assert value['omega_rad_s']==[1,2,10]
    results['response']={'omega_rad_s':[1,2,10],'magnitude_db':[0,-6,-20]}
    assert control_composition.bode(data,results)['state']=='pass'
    assert control_composition.bode({**data,'criteria':[]},results)['state']=='unassessed'


def test_pole_composition_keeps_original_state_basis_and_sampled_failures():
    system={'A':[[1,2],[3,4]],'state_units':['m','m/s']}
    data={'system':system,'control_period_s':.015,'desired_poles_per_s':[-2,-4]}
    results={};jobs=control_composition.pole_jobs(data,results)
    next(jobs);results['plant']={'system':system,'transfer_function':{'sentinel':'tf'}}
    _,skill,value=next(jobs)
    assert skill=='state-feedback-gain-synthesis' and value['system'] is system
    assert value['control_period_s']==.015
    results['feedback']={'continuous_stable':True,'sampled_stable':False,'K':[[7,8]]}
    assert control_composition.pole(data,results)['state']=='fail'


def test_actuator_composition_connects_loss_and_temperature_in_order():
    data={'units':'SI','data_basis':'synthetic_validation','thermal_resistance_K_W':10,
          'thermal_capacity_J_K':5,'maximum_winding_K':350,
          'modes':[{'name':'a','duration_s':2},{'name':'b','duration_s':3}]}
    results={};jobs=electrical.jobs(data,results)
    role,skill,_=next(jobs);results[role]={'copper_W':7}
    role,skill,value=next(jobs)
    assert skill=='first-order-thermal-response' and value['heat_W']==7
    results[role]={'end_K':321}
    role,_,_=next(jobs);results[role]={'copper_W':4}
    _,_,value=next(jobs)
    assert value['initial_K']==321 and value['heat_W']==4 and value['duration_s']==3


def test_composite_run_retains_and_hash_binds_all_dependency_results(tmp_path):
    source=REPO/'skills/engineering/pole-placement-design/examples/input.json'
    receipt=run('pole-placement-design',source,tmp_path/'run')
    assert receipt['contract']['kind']=='composite'
    assert {r['skill'] for r in receipt['dependencies']}=={'transfer-function-derivation','state-feedback-gain-synthesis'}
    for reference in receipt['dependencies']:
        result=tmp_path/'run'/reference['result_path']
        assert hashlib.sha256(result.read_bytes()).hexdigest()==reference['result_sha256']
        assert hashlib.sha256((result.parent/'receipt.json').read_bytes()).hexdigest()==reference['receipt_sha256']
        child=json.loads(result.read_text())
        assert child['skill']==reference['skill'] and child['schema_version']==1
    from tools.engineering_skills.live_acceptance import verify_lineage
    assert verify_lineage(tmp_path/'run')==3
    result.write_text(result.read_text()+' ')
    with pytest.raises(ValueError,match='hash'):verify_lineage(tmp_path/'run')


def test_dependency_failure_is_retained_and_parent_cannot_claim_completion(tmp_path):
    data=json.loads((REPO/'skills/engineering/pole-placement-design/examples/input.json').read_text())
    data['system']['B']=[[0],[0]]
    p=tmp_path/'input.json';p.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='controllable'):run('pole-placement-design',p,tmp_path/'out')
    receipt=json.loads((tmp_path/'out/receipt.json').read_text())
    assert receipt['status']=='failed' and receipt['dependencies'][-1]['status']=='failed'
    assert not (tmp_path/'out/result.json').exists()
    assert (tmp_path/'out/dependencies/plant/result.json').exists()


def test_composite_cli_response_stays_small_without_truncating_saved_evidence(monkeypatch,capsys,tmp_path):
    from tools.engineering_skills.runner import main
    import sys
    source=REPO/'skills/engineering/cube-gnc-loop-analysis/examples/input.json'
    monkeypatch.setattr(sys,'argv',['ea-engineering','run','cube-gnc-loop-analysis','--input',str(source),'--output',str(tmp_path/'out')])
    main()
    raw=capsys.readouterr().out
    result=json.loads(raw)
    assert len(raw)<2048 and result['status']=='completed' and result['dependency_count']==3
    receipt=json.loads((tmp_path/'out/receipt.json').read_text())
    assert len(receipt['artifacts'])>20


def test_generic_bode_plot_carries_the_supplied_transfer_units(monkeypatch,tmp_path):
    from tools.engineering_skills.runner import plot_results
    from matplotlib.axes import Axes
    labels=[];original=Axes.set_ylabel
    def record(axis,label,*args,**kwargs):
        labels.append(label)
        return original(axis,label,*args,**kwargs)
    monkeypatch.setattr(Axes,'set_ylabel',record)
    plot_results('bode-diagram-analysis',{'bode':{'omega_rad_s':[1,2],
        'magnitude_db':[-3,-6],'phase_deg':[-45,-60],'magnitude_reference':'1 m/N'}},tmp_path)
    assert any('1 m/N' in label for label in labels)
    assert all('rad/N' not in label for label in labels)
