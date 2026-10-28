import hashlib
import json
from pathlib import Path
import pytest
from tools.engineering_skills.runner import run, verify_canonical_requirements

SKILLS=Path(__file__).resolve().parents[2]/'skills/engineering'


def test_real_cli_artifact_integrity_and_no_overwrite(tmp_path):
    p=SKILLS/'requirement-evidence-assessment/examples/input.json'
    receipt=run('systems',p,tmp_path/'out')
    assert receipt['status']=='completed'
    result=json.loads((tmp_path/'out/result.json').read_text())
    assert result['requirements'][0]['state']=='inconclusive'
    assert receipt['artifacts']['result.json']==hashlib.sha256((tmp_path/'out/result.json').read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):run('systems',p,tmp_path/'out')


def test_bad_hash_and_forged_verified_flag_are_overridden(tmp_path):
    data=json.loads((SKILLS/'requirement-evidence-assessment/examples/input.json').read_text())
    data['evidence'][0]['artifact_verified']=True
    data['evidence'][0]['artifact']['sha256']='0'*64
    p=tmp_path/'input.json';p.write_text(json.dumps(data))
    run('systems',p,tmp_path/'out')
    result=json.loads((tmp_path/'out/result.json').read_text())
    assert 'missing_or_bad_artifact_hash' in result['requirements'][0]['evidence'][0]['reasons']


def test_verified_artifact_binds_metric_and_execution_metadata(tmp_path):
    example=SKILLS/'requirement-evidence-assessment/examples'
    data=json.loads((example/'input.json').read_text())
    record=json.loads((example/'simulation.json').read_text())
    artifact=tmp_path/'metric.json';artifact.write_bytes((example/'simulation.json').read_bytes())
    data['evidence'][0]['artifact']['path']='metric.json'
    data['requirements'][0]['data']['acceptance_criteria']['domain']='simulation'
    p=tmp_path/'input.json'
    def check(name):
        p.write_text(json.dumps(data));run('systems',p,tmp_path/name)
        return json.loads((tmp_path/name/'result.json').read_text())['requirements'][0]
    data['evidence'][0]['value']=30
    r=check('forged-value')
    assert r['state']=='inconclusive' and 'metric_not_bound_to_artifact' in r['evidence'][0]['reasons']
    data['evidence'][0]['value']=6
    assert check('actual-value')['state']=='fail'
    data['requirements'][0]['data']['acceptance_criteria']['value']=6
    assert check('valid-pass')['state']=='pass'
    data['evidence'][0]['configuration_digest']='b'*64
    assert check('stale-metadata')['state']=='inconclusive'
    data['evidence'][0]['configuration_digest']='a'*64
    record['status']='failed';raw=json.dumps(record).encode();artifact.write_bytes(raw)
    data['evidence'][0]['artifact']['sha256']=hashlib.sha256(raw).hexdigest()
    r=check('mismatched-status')
    assert r['state']=='inconclusive' and 'metric_not_bound_to_artifact' in r['evidence'][0]['reasons']


def test_unrecognized_artifact_and_ineligible_failed_row_do_not_override_pass(tmp_path):
    example=SKILLS/'requirement-evidence-assessment/examples'
    data=json.loads((example/'input.json').read_text())
    data['requirements'][0]['data']['acceptance_criteria'].update(domain='simulation',value=6)
    data['evidence'][0]['artifact']['path']='valid.json'
    (tmp_path/'valid.json').write_bytes((example/'simulation.json').read_bytes())
    stale=dict(data['evidence'][0],id='stale',status='failed',configuration_digest='b'*64,
               artifact={'path':'other.json','sha256':hashlib.sha256(b'{"hold_duration_s": 6}').hexdigest()})
    (tmp_path/'other.json').write_bytes(b'{"hold_duration_s": 6}')
    data['evidence'].append(stale)
    p=tmp_path/'input.json';p.write_text(json.dumps(data));run('systems',p,tmp_path/'out')
    result=json.loads((tmp_path/'out/result.json').read_text())['requirements'][0]
    assert result['state']=='pass'
    assert result['evidence'][1]['state']=='inconclusive' and 'metric_not_bound_to_artifact' in result['evidence'][1]['reasons']


def test_failures_keep_a_receipt_and_non_synthetic_requires_ssot(tmp_path):
    p=tmp_path/'bad.json';p.write_text(json.dumps({'units':'wrong','data_basis':'assumed'}))
    with pytest.raises(ValueError):run('gnc',p,tmp_path/'out')
    assert json.loads((tmp_path/'out/receipt.json').read_text())['status']=='failed'
    with pytest.raises(ValueError, match='requires --store'):
        verify_canonical_requirements({'data_basis':'derived'},None)


@pytest.mark.parametrize('discipline,skill',[
    ('gnc','cube-gnc-loop-analysis'),('mechanical','mass-property-uncertainty'),
    ('electrical','actuator-duty-cycle-analysis')])
def test_all_scientific_examples_produce_json_and_plots(tmp_path,discipline,skill):
    receipt=run(discipline,SKILLS/skill/'examples/input.json',tmp_path/'out')
    assert receipt['status']=='completed'
    assert list((tmp_path/'out').glob('*.png'))


def test_canonical_payload_tampering_is_rejected(monkeypatch,tmp_path):
    import sys
    import types
    original={'project_id':'generic-project','id':'R','revision':'1','kind':'requirement','data':{'value':30}}
    class Store:
        def __init__(self,path):pass
        def check(self,project):return {'ok':True}
        def records(self,project,kinds):return [original]
    monkeypatch.setitem(sys.modules,'onepiece',types.SimpleNamespace(Store=Store))
    assert verify_canonical_requirements({'data_basis':'derived','requirements':[original]},tmp_path)['verified']
    with pytest.raises(ValueError,match='canonical'):
        verify_canonical_requirements({'data_basis':'derived','requirements':[{**original,'data':{'value':6}}]},tmp_path)
