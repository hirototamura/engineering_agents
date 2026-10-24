"""Post-run publication preserves saved gains, revisions and retry identity."""
import copy
import hashlib
import json
import tarfile

import pytest

from scenario.balancing_cube.design import digest
from tools import finalize_cube_workflow_study as finalizer


@pytest.mark.parametrize('preexisting_audit',[True,False])
def test_finalization_preserves_controller_and_is_idempotent(tmp_path, monkeypatch, preexisting_audit):
    onepiece = pytest.importorskip('onepiece')
    root = tmp_path/'study'
    store = onepiece.Store(root/'record-store')
    study_id = 'publication-test'
    compiled = {'input_digest':'original-input', 'config':{'physics':{'dt':.001}},
                'controller':{'K':[[1., 2.]], 'control_period_s':.015}}
    def record(id, kind, data):
        return onepiece.make_record(project_id='balancing-cube', id=id, kind=kind, data=data)
    initial = [record('source', 'simulation_snapshot', {}),
               record(study_id+'.fresh-confirmation', 'test_case', {}),
               record('run.candidate.2', 'design_candidate', {'input_digest':'original-input'}),
               *([record(study_id+'.fresh.'+mode, 'simulation_run', {'score':.9})
                 for mode in ('multi_agent','single_agent')] if preexisting_audit else [])]
    store.import_records(initial)
    initial_ids = [p.name for p in store.commits.iterdir() if p.is_dir()]
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    summary = {'state':'inconclusive', 'study_id':study_id,
               'arms':{m:{'iterations_completed':9,'proposal_rounds_recorded':10,'run_id':'run',
                          'validation':{'candidate_ref':{'id':'run.candidate.2','revision':'1'}}}
                       for m in ('multi_agent','single_agent')},
               'fresh_audit':{}}
    write(root/'study-results.json', summary)
    write(root/'study-manifest.json', {})
    write(root/'initial-commit-ids.json', initial_ids)
    write(root/'verifier/frozen-audit-snapshot.json', {'source_snapshot_ref':{'id':'source','revision':'1'}})
    write(root/'multi_agent/candidates/candidate-002/compiled.json', compiled)
    write(root/'multi_agent/candidates/candidate-002/result.json', {'matrix_cell':'starting_design'})
    for mode in ('multi_agent','single_agent'):
        write(root/mode/'validation/compiled.json',compiled)
        audit_input=copy.deepcopy(compiled)
        audit_input['input_digest']=digest({'config':compiled['config'],'controller':compiled['controller'],'snapshot_digest':'new-seed-partition'})
        if preexisting_audit:
            write(root/'fresh-audit'/mode/'compiled.json',audit_input)
            write(root/'fresh-audit'/mode/'result.json',{'input_digest':audit_input['input_digest'],
                'snapshot_digest':'new-seed-partition','score':.9,'records':[]})
    received = []
    class AuditAdapter:
        frozen_digest = 'new-seed-partition'
        def __init__(self, snapshot):
            self.snapshot = snapshot
        def rollout(self, value, **kwargs):
            received.append(copy.deepcopy(value))
            assert kwargs['stage']=='validation' and kwargs['require_gpu'] is True
            return {'input_digest':value['input_digest'], 'snapshot_digest':self.frozen_digest,
                    'score':.91, 'screening_pass_fraction':1., 'records':[], 'physical_verified':False}
    monkeypatch.setattr(finalizer, 'BalancingCubeAdapter', AuditAdapter)
    info = finalizer.finalize(root)
    assert received[0]['controller']==compiled['controller']
    assert received[0]['config']==compiled['config']
    assert received[0]['input_digest']!=compiled['input_digest']
    assert json.loads((root/'multi_agent/candidates/candidate-002/compiled.json').read_text())==compiled
    records = onepiece.Store(store.path).records('balancing-cube')
    for mode in ('multi_agent','single_agent'):
        versions = {r['revision']:r for r in records if r['id']==study_id+'.fresh.'+mode}
        if preexisting_audit:
            assert versions['1']['data']=={'score':.9}
        else:
            assert versions['1']['data']['postprocessing_note']
        assert versions['2']['data']['snapshot_ref']=={'id':study_id+'.audit-snapshot','revision':'1'}
    assert onepiece.Store(store.path).check()['ok']
    assert json.loads((root/'study-results.json').read_text())==summary
    postprocessed=json.loads((root/'postprocess-results.json').read_text())
    assert postprocessed['state']=='inconclusive'
    assert postprocessed['arms']['multi_agent']['iterations_completed']==9
    assert postprocessed['attempted_cycles_complete'] is True
    assert finalizer.finalize(root)==info
    assert len(received)==(1 if preexisting_audit else 3)
    archive = tmp_path/'study-results.tar.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==info['sha256']
    with tarfile.open(archive) as bundle:
        names = bundle.getnames()
    assert not any(name.startswith(('study/stores/', 'study/record-store/')) for name in names)
    assert any(name.startswith('delta-commits/') for name in names)
    assert not any('/'+id+'/' in name for id in initial_ids for name in names)
    # A retry cannot quietly replace the saved audit controller.
    changed = copy.deepcopy(received[0]); changed['controller']['K']=[[99.]]
    write(root/'baseline-fresh-audit/compiled.json', changed)
    with pytest.raises(ValueError, match='configuration differs'):
        finalizer.finalize(root)


def test_finalization_refuses_an_incomplete_pair(tmp_path):
    pytest.importorskip('onepiece')
    (tmp_path/'study-results.json').write_text(json.dumps({'state':'inconclusive','arms':{}}))
    with pytest.raises(ValueError, match='Both ten-round arms'):
        finalizer.finalize(tmp_path)
