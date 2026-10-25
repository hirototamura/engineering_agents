import copy
import pytest
from environment.engineering_analysis.systems import analyze


def case():
    ref={'id':'req','revision':'1'};design={'id':'design','revision':'1'}
    return {'data_basis':'synthetic_validation','configuration_digest':'a'*64,'design_ref':design,
            'requirements':[{'id':'req','revision':'1','data':{'approval_state':'human_reviewed','conditions':['corner000'],
                 'acceptance_criteria':{'domain':'simulation','metric':'hold','operator':'>=','value':30,'unit':'s'}}}],
            'evidence':[{'id':'run','requirement_ref':ref,'design_ref':design,'configuration_digest':'a'*64,'artifact_verified':True,
                         'domain':'simulation','metric':'hold','value':30,'unit':'s','conditions':['corner000'],'status':'completed'}]}


def test_known_pass_and_failed_threshold_or_execution():
    d=case();assert analyze(d)['all_evaluable_requirements_pass']
    d['evidence'][0]['value']=6;assert analyze(d)['requirements'][0]['state']=='fail'
    d['evidence'][0]['status']='failed';assert analyze(d)['requirements'][0]['state']=='fail'


@pytest.mark.parametrize('change',[{'domain':'hardware'},{'unit':'ms'},{'configuration_digest':'b'*64},{'conditions':[]},{'artifact_verified':False}])
def test_ineligible_evidence_is_never_accepted(change):
    d=case();d['evidence'][0].update(change)
    assert analyze(d)['requirements'][0]['state']=='inconclusive'


def test_old_revision_open_conditions_and_missing_evidence():
    d=case();d['evidence'][0]['requirement_ref']['revision']='old'
    assert analyze(d)['requirements'][0]['state']=='not_run'
    d=case();d['requirements'][0]['data']['unresolved_items']=['floor undefined']
    assert analyze(d)['requirements'][0]['state']=='inconclusive'
    d=case();d['requirements'][0]['data']['acceptance_criteria']['domain']='hardware';d['evidence'][0]['value']=6
    r=analyze(d);assert r['requirements'][0]['state']=='inconclusive' and not r['physical_verified']


def test_failed_evidence_cannot_be_hidden_by_success():
    d=case();bad=copy.deepcopy(d['evidence'][0]);bad['id']='failed';bad['value']=5;d['evidence'].append(bad)
    assert analyze(d)['requirements'][0]['state']=='fail'
