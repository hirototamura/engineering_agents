"""Audit the frozen starting design and package a finished study with a store delta.

This runs after both design arms stop. It never feeds fresh outcomes back into
proposal generation, edits requirement records, or establishes a human baseline.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import time

from integrations.one_piece.mechanical_bridge import atomic_json
from scenario.balancing_cube.adapter import BalancingCubeAdapter
from scenario.balancing_cube.design import digest


def finalize(root, *, preflight_root=None):
    from onepiece import Store, make_record
    root=Path(root).resolve()
    summary=json.loads((root/'study-results.json').read_text())
    if set(summary['arms'])!={'multi_agent','single_agent'} or any(
            a.get('proposal_rounds_recorded',a.get('iterations_completed'))!=10 for a in summary['arms'].values()):
        raise ValueError('Both ten-round arms must finish before final fresh baseline audit')
    manifest=json.loads((root/'study-manifest.json').read_text())
    snapshot=json.loads((root/'verifier/frozen-audit-snapshot.json').read_text())
    adapter=BalancingCubeAdapter(snapshot)
    # A malformed proposal is an observed outcome of an attempted cycle. Keep
    # the original dispatch status and counts. It need not suppress an audit of
    # the frozen selection after all ten attempts in both arms have stopped.
    for mode in ('multi_agent','single_agent'):
        selected=json.loads((root/mode/'validation/compiled.json').read_text())
        saved_controller=digest(selected['controller'])
        selected['input_digest']=digest({'config':selected['config'],'controller':selected['controller'],'snapshot_digest':adapter.frozen_digest})
        directory=root/'fresh-audit'/mode
        if (directory/'result.json').exists():
            audited=json.loads((directory/'result.json').read_text())
            if json.loads((directory/'compiled.json').read_text())!=selected:
                raise ValueError('Selected audit configuration differs from saved selection')
        else:
            atomic_json(directory/'compiled.json',selected)
            audited=adapter.rollout(selected,stage='validation',require_gpu=True,deadline=time.monotonic()+1800)
            atomic_json(directory/'result.json',audited)
        if audited['input_digest']!=selected['input_digest'] or audited['snapshot_digest']!=adapter.frozen_digest:
            raise ValueError('Selected audit result differs from frozen inputs')
        assert digest(selected['controller'])==saved_controller
        summary['fresh_audit'][mode]={k:v for k,v in audited.items()if k!='records'}
    candidates=root/'multi_agent/candidates'
    selected_path=next(path for path in sorted(candidates.glob('*/compiled.json'))
        if json.loads(path.with_name('result.json').read_text())['matrix_cell']=='starting_design')
    compiled=json.loads(selected_path.read_text())
    original_input=compiled['input_digest'];original_controller=digest(compiled['controller'])
    compiled['input_digest']=digest({'config':compiled['config'],'controller':compiled['controller'],'snapshot_digest':adapter.frozen_digest})
    audit=root/'baseline-fresh-audit'
    if (audit/'compiled.json').exists():
        if json.loads((audit/'compiled.json').read_text())!=compiled:
            raise ValueError('Frozen starting audit configuration differs on retry')
    else:
        atomic_json(audit/'compiled.json',compiled)
    if (audit/'result.json').exists():
        result=json.loads((audit/'result.json').read_text())
        if result['input_digest']!=compiled['input_digest'] or result['snapshot_digest']!=adapter.frozen_digest:
            raise ValueError('Existing audit result differs from the frozen inputs')
    else:
        result=adapter.rollout(compiled,stage='validation',require_gpu=True,deadline=time.monotonic()+1800)
        atomic_json(audit/'result.json',result)
    assert digest(compiled['controller'])==original_controller
    store=Store(root/'record-store')
    initial_ids=set(json.loads((root/'initial-commit-ids.json').read_text()))
    if preflight_root:
        # Preserve the earlier tokenizer-refused run as inconclusive history.
        # It had zero completed design rounds and is excluded from this pair.
        source=Path(preflight_root)/'record-store/commits'
        if source.exists():
            for folder in sorted(source.iterdir()):
                if folder.is_dir() and folder.name not in initial_ids and not (store.commits/folder.name).exists():
                    shutil.copytree(folder,store.commits/folder.name,copy_function=shutil.copy2)
        store=Store(store.path)
    def artifact(path):
        raw=path.read_bytes()
        return {'path':path.relative_to(root).as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw)}
    def publish(record):
        path=root/'publication'/f"{record['id']}@{record['revision']}.json"
        if path.exists():
            prior=json.loads(path.read_text())
            if any(prior[k]!=record[k]for k in ('data','links','artifacts','kind','product_node','actor')):
                raise ValueError('Conflicting postprocess record on retry')
            record=prior
        else:
            atomic_json(path,record)
        return store.import_records([record],artifacts_root=root)
    study_id=summary['study_id']
    snapshot_record=make_record(project_id='balancing-cube',id=study_id+'.audit-snapshot',kind='simulation_snapshot',revision='1',
        product_node='cube.verification',actor={'type':'automation','id':'workflow-study-verifier'},data=copy.deepcopy(snapshot),
        links=[{'type':'derive','target':snapshot['source_snapshot_ref']}],artifacts=[artifact(root/'verifier/frozen-audit-snapshot.json')])
    snapshot_ref={'id':snapshot_record['id'],'revision':'1'}
    publish(snapshot_record)
    source_run=summary['arms']['multi_agent']['run_id']
    parent=next(r for r in store.records('balancing-cube',['design_candidate'])
        if r['id'].startswith(source_run+'.candidate.') and r['data']['input_digest']==original_input)
    case_ref={'id':study_id+'.fresh-confirmation','revision':'1'}
    baseline_record=make_record(project_id='balancing-cube',id=study_id+'.fresh.starting-design',kind='simulation_run',revision='1',
        product_node='cube.verification',actor={'type':'automation','id':'workflow-study-verifier'},
        data={**{k:v for k,v in result.items()if k!='records'},'snapshot_ref':snapshot_ref,
              'candidate_ref':{'id':parent['id'],'revision':parent['revision']},'comparison_role':'common starting design',
              'saved_controller_digest':original_controller,'physical_verified':False},
        links=[{'type':'verify','target':case_ref,'scope':'fresh-seed numerical development comparison only'}],
        artifacts=[artifact(audit/'compiled.json'),artifact(audit/'result.json')])
    publish(baseline_record)
    # Add exact audit-snapshot references as new metadata revisions; preserve
    # the original measured JSON and revision 1 without alteration.
    for mode in ('multi_agent','single_agent'):
        previous=next((r for r in store.records('balancing-cube',['simulation_run'])if r['id']==study_id+'.fresh.'+mode and r['revision']=='1'),None)
        if previous is None:
            selected=json.loads((root/mode/'validation/compiled.json').read_text())
            previous=make_record(project_id='balancing-cube',id=study_id+'.fresh.'+mode,kind='simulation_run',revision='1',
                product_node='cube.verification',actor={'type':'automation','id':'workflow-study-verifier'},
                data={**summary['fresh_audit'][mode],'arm':mode,'snapshot_ref':snapshot_ref,
                      'candidate_ref':summary['arms'][mode]['validation'].get('candidate_ref'),
                      'saved_controller_digest':digest(selected['controller']),
                      'source_run_id':summary['arms'][mode]['run_id'],
                      'postprocessing_note':'All ten proposal attempts stopped before this audit. Rejected cycles remain rejected.',
                      'physical_verified':False},
                links=[{'type':'verify','target':case_ref,'scope':'fresh-seed numerical development evidence only'}],
                artifacts=[artifact(root/'fresh-audit'/mode/'compiled.json'),artifact(root/'fresh-audit'/mode/'result.json')])
            publish(previous)
        revised=make_record(project_id='balancing-cube',id=previous['id'],kind='simulation_run',revision='2',
            product_node=previous['product_node'],actor={'type':'automation','id':'workflow-study-verifier'},
            data={**previous['data'],'snapshot_ref':snapshot_ref,'metadata_revision_note':'Exact frozen audit snapshot link added; no rerun or change to measured outcomes.'},
            links=[*previous['links'],{'type':'derive','target':{'id':previous['id'],'revision':'1'}}],artifacts=previous['artifacts'])
        publish(revised)
    aggregate=make_record(project_id='balancing-cube',id=study_id+'.paired-study',kind='analysis_result',revision='1',
        product_node='cube.system',actor={'type':'automation','id':'workflow-study-analysis'},
        data={'scenario':'balancing_cube_workflow_study','status':summary['state'],'study_id':study_id,'attempted_iterations_per_arm':10,
              'arms':summary['arms'],'fresh_audit':summary['fresh_audit'],
              'starting_design_fresh_audit':{k:v for k,v in result.items()if k!='records'},
              'audit_snapshot_ref':snapshot_ref,'one_paired_pilot':True,'model_weights_updated':False,'physical_verified':False},
        artifacts=[artifact(root/'study-results.json'),artifact(root/'study-manifest.json'),artifact(audit/'result.json')])
    publish(aggregate)
    check=store.check('balancing-cube')
    if not check['ok']:raise ValueError('Final record store check failed: '+str(check['errors']))
    new_ids=sorted(set(p.name for p in store.commits.iterdir()if p.is_dir()and not p.name.startswith('.'))-initial_ids)
    atomic_json(root/'postprocess-results.json',{**summary,'attempted_cycles_complete':True,
        'postprocessing_note':'Fresh audit added after both arms stopped; original dispatch status and completed-cycle counts preserved.'})
    atomic_json(root/'finalization.json',{'state':'completed','study_state':summary['state'],'new_commit_ids':new_ids,'baseline_controller_preserved':True,
        'starting_design_fresh_score':result['score'],'starting_design_fresh_pass_fraction':result['screening_pass_fraction'],
        'store_check':{k:v for k,v in check.items()if k!='warnings'}})
    archive=root.parent/(root.name+'-results.tar.gz')
    archive_manifest=root.parent/'result-archive.json'
    if archive.exists() and archive_manifest.exists():
        previous=json.loads(archive_manifest.read_text())
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=previous['sha256']:
            raise ValueError('Existing result archive hash mismatch')
        return previous
    with tarfile.open(archive,'w:gz')as tar:
        for path in sorted(root.rglob('*')):
            relative=path.relative_to(root)
            if not path.is_file()or path.is_symlink()or relative.parts[0]in {'stores','record-store'}:continue
            tar.add(path,arcname=(Path('study')/relative).as_posix(),recursive=False)
        for name in new_ids:
            folder=store.commits/name
            for path in sorted(folder.rglob('*')):
                if path.is_file()and not path.is_symlink():
                    tar.add(path,arcname=(Path('delta-commits')/name/path.relative_to(folder)).as_posix(),recursive=False)
    info={'path':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size,'new_commits':len(new_ids)}
    atomic_json(root.parent/'result-archive.json',info)
    return info


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--preflight-root',type=Path);a=p.parse_args()
    print(json.dumps(finalize(a.root,preflight_root=a.preflight_root)))


if __name__=='__main__':main()
