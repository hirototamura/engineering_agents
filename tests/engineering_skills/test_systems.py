import copy
import pytest
from environment.engineering_analysis.systems import analyze, BOUND_FIELDS, METRIC_SCHEMA


def case():
    ref={'id':'req','revision':'1'};design={'id':'design','revision':'1'}
    return {'data_basis':'synthetic_validation','configuration_digest':'a'*64,'design_ref':design,
            'requirements':[{'id':'req','revision':'1','data':{'approval_state':'human_reviewed','conditions':['corner000'],
                 'acceptance_criteria':{'domain':'simulation','metric':'hold','operator':'>=','value':30,'unit':'s'}}}],
            'evidence':[{'id':'run','requirement_ref':ref,'design_ref':design,'configuration_digest':'a'*64,
                         'domain':'simulation','metric':'hold','value':30,'unit':'s','conditions':['corner000'],'status':'completed'}]}


def assess(data):
    verified={i:{'hash_verified':True,'record':{'schema':METRIC_SCHEMA,**{k:e[k] for k in (*BOUND_FIELDS,'value')}}}
              for i,e in enumerate(data['evidence'])}
    return analyze(data,verified)


def test_known_pass_and_failed_threshold_or_execution():
    d=case();assert assess(d)['all_evaluable_requirements_pass']
    d['evidence'][0]['value']=6;assert assess(d)['requirements'][0]['state']=='fail'
    d['evidence'][0]['status']='failed';assert assess(d)['requirements'][0]['state']=='fail'


def test_eligible_failed_execution_can_have_no_metric_value():
    d=case();d['evidence'][0].update(status='failed',value=None)
    result=assess(d)['requirements'][0]
    assert result['state']=='fail' and result['evidence'][0]['eligible']


@pytest.mark.parametrize('change',[{'domain':'hardware'},{'unit':'ms'},{'configuration_digest':'b'*64},{'conditions':[]}])
def test_ineligible_evidence_is_never_accepted(change):
    d=case();d['evidence'][0].update(change)
    assert assess(d)['requirements'][0]['state']=='inconclusive'


def test_old_revision_open_conditions_and_missing_evidence():
    d=case();d['evidence'][0]['requirement_ref']['revision']='old'
    assert assess(d)['requirements'][0]['state']=='not_run'
    d=case();d['requirements'][0]['data']['unresolved_items']=['floor undefined']
    assert assess(d)['requirements'][0]['state']=='inconclusive'
    d=case();d['requirements'][0]['data']['acceptance_criteria']['domain']='hardware';d['evidence'][0]['value']=6
    r=assess(d);assert r['requirements'][0]['state']=='inconclusive' and not r['physical_verified']


def test_failed_evidence_cannot_be_hidden_by_success():
    d=case();bad=copy.deepcopy(d['evidence'][0]);bad['id']='failed';bad['value']=5;d['evidence'].append(bad)
    assert assess(d)['requirements'][0]['state']=='fail'


@pytest.mark.parametrize('change',[{'domain':'hardware'},{'unit':'ms'},
    {'configuration_digest':'b'*64},{'conditions':[]}])
def test_ineligible_failed_evidence_does_not_override_eligible_pass(change):
    d=case();bad=copy.deepcopy(d['evidence'][0]);bad.update(id='old-failure',status='failed',**change)
    d['evidence'].append(bad)
    result=assess(d)['requirements'][0]
    assert result['state']=='pass'
    assert result['evidence'][1]['state']=='inconclusive' and not result['evidence'][1]['eligible']


@pytest.mark.parametrize('unsupported',[True,'ready',None, float('nan')])
def test_unsupported_criterion_remains_inconclusive_and_other_requirements_run(unsupported):
    d=case();second=copy.deepcopy(d['requirements'][0]);second['id']='other'
    d['requirements'].append(second);other=copy.deepcopy(d['evidence'][0]);other['id']='other-run';other['requirement_ref']={'id':'other','revision':'1'}
    d['evidence'].append(other);d['requirements'][0]['data']['acceptance_criteria']['value']=unsupported
    result=assess(d)['requirements']
    assert result[0]['state']=='inconclusive'
    assert 'criterion_not_machine_evaluable' in result[0]['evidence'][0]['reasons']
    assert result[1]['state']=='pass'


def test_input_flags_are_not_evidence():
    d=case();d['evidence'][0]['artifact_verified']=True
    assert analyze(d)['requirements'][0]['state']=='inconclusive'


def test_failed_evidence_with_bad_hash_does_not_override_pass():
    d=case();bad=copy.deepcopy(d['evidence'][0]);bad.update(id='bad-hash',status='failed');d['evidence'].append(bad)
    good=d['evidence'][0]
    verified={0:{'hash_verified':True,'record':{'schema':METRIC_SCHEMA,**{k:good[k] for k in (*BOUND_FIELDS,'value')}}}}
    result=analyze(d,verified)['requirements'][0]
    assert result['state']=='pass' and result['evidence'][1]['state']=='inconclusive'
    assert 'missing_or_bad_artifact_hash' in result['evidence'][1]['reasons']


@pytest.mark.parametrize('value',[True,'six',None])
def test_unsupported_metric_value_remains_inconclusive(value):
    d=case();d['evidence'][0]['value']=value
    result=assess(d)['requirements'][0]
    assert result['state']=='inconclusive'
    assert 'metric_not_machine_evaluable' in result['evidence'][0]['reasons']
