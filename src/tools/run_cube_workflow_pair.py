"""Run the predeclared ten-round workflow study through normal EA dispatch.

Both arms receive isolated copies of one immutable initial One-Piece store,
identical historical seed runs and a common starting proposal. Fresh-seed audit
conditions are withheld from prompt construction until both arms finish.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from integrations.one_piece.mechanical_bridge import MechanicalBridge, atomic_json
from scenario.balancing_cube.adapter import BalancingCubeAdapter
from scenario.balancing_cube.design import digest
from scenario.balancing_cube.workflow import ROLE_CAPS


def commit_names(path):
    return sorted(p.name for p in (Path(path) / 'commits').iterdir() if p.is_dir() and not p.name.startswith('.'))


def clone_store(source, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    # Only immutable commit objects are shared. SQLite and locks are never linked.
    shutil.copytree(Path(source) / 'commits', destination / 'commits', copy_function=os.link)


def run(input_manifest, output):
    from core.llm.factory import build_llm_client
    from onepiece import Store, make_record
    from scenario.runner import run_scenario
    from environment.mujoco.multi_gpu import shutdown_workers
    plan = json.loads(Path(input_manifest).read_text())
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    initial_store = Path(plan['initial_store']).resolve()
    ids = commit_names(initial_store)
    commit_set_sha = hashlib.sha256(('\n'.join(ids) + '\n').encode()).hexdigest()
    if commit_set_sha != plan['initial_commit_set_sha256']:
        raise ValueError('Initial store commit set differs from the predeclared plan')
    store = Store(initial_store)
    check = store.check('balancing-cube')
    if not check['ok']:
        raise ValueError('Initial One-Piece integrity check failed')
    initial_proposal = Path(plan['initial_proposal_path']).resolve()
    if hashlib.sha256(initial_proposal.read_bytes()).hexdigest() != plan['initial_proposal_sha256']:
        raise ValueError('Starting design hash mismatch')
    for source in plan['seed_sources']:
        if hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Historical seed artifact mismatch: ' + source['path'])
    client = build_llm_client(plan['llm'])
    if not client.check_connection():
        raise ValueError('Declared LLM endpoint is unavailable')
    import requests
    model_info = requests.get(client.base_url + '/models', timeout=15).json()
    model = next(m for m in model_info['data'] if m['id'] == plan['llm']['model'])
    if model['root'] != plan['model_root']:
        raise ValueError('Served model weights differ from the declared model')
    manifest = {**plan, 'started_at': datetime.now(timezone.utc).isoformat(),
                'verified_model': model, 'initial_store_check': {k:v for k,v in check.items() if k!='warnings'},
                'reference': 'https://arxiv.org/abs/2610.12176',
                'model_weights_updated': False, 'completion_caps': ROLE_CAPS,
                'fresh_audit_disclosure': 'Withheld from all LLM prompts until both ten-round arms finish',
                'authority': 'Development simulation only; no requirement or adopted-baseline changes'}
    atomic_json(output / 'study-manifest.json', manifest)
    sampler = subprocess.Popen([sys.executable, '-m', 'tools.gpu_telemetry', '--output', str(output / 'gpu-telemetry.jsonl')])
    bridge = MechanicalBridge(initial_store, snapshot_revision=plan['snapshot_revision'])
    snapshot = bridge.load_snapshot()
    audit_snapshot = copy.deepcopy(snapshot)
    audit_snapshot['plan']['validation']['seeds'] = plan['fresh_confirmation_seeds']
    atomic_json(output / 'verifier/frozen-audit-snapshot.json', audit_snapshot)
    arms = {}
    try:
        # Warm the shared MJX executable before either arm's timed campaign.
        adapter = BalancingCubeAdapter(snapshot)
        compiled = adapter.compile({'id':'common-warmup','family':'reference','parameters':{},'hypothesis':'Warm identical execution paths before both arms'})
        atomic_json(output / 'warmup/compiled.json', compiled)
        warmup = adapter.rollout(compiled, require_gpu=True, deadline=time.monotonic()+1800)
        atomic_json(output / 'warmup/result.json', warmup)
        if warmup['gpu_state'] != 'completed':
            raise RuntimeError('Required GPU warmup did not execute')
        for mode in plan['arm_order']:
            arm_store, arm_output = output / 'stores' / mode, output / mode
            arm_store.parent.mkdir(exist_ok=True)
            clone_store(initial_store, arm_store)
            overrides = {'backend':{'kind':'mjx_gpu'}, 'ssot':{'path':str(arm_store),'snapshot_revision':plan['snapshot_revision']},
                'agents':{'mode':'llm','llm':plan['llm']},
                'iteration':{'enabled':True,'count':10,'max_candidates':42,'max_wall_s':7200,'stagnation_rounds':10,'proposal_retries':0},
                'workflow':{'enabled':True,'mode':mode,'prompt_token_cap':140000,'initial_proposal_path':str(initial_proposal)},
                'memory':{'enabled':True,'seed_runs':plan['seed_runs']}}
            os.environ['EA_LLM_TRACE_DIR'] = str(arm_output / 'llm-trace')
            atomic_json(output / f'{mode}-overrides.json', overrides)
            atomic_json(output / 'status.json', {'state':'running','active_arm':mode,'completed_arms':list(arms)})
            try:
                # Normal EA scenario dispatch. No duplicate simulation engine.
                run_scenario('balancing_cube', output_dir=arm_output, overrides=overrides,
                             recreate_output=False, run_id=plan['study_id']+'-'+mode)
                arms[mode] = json.loads((arm_output / 'summary.json').read_text())
            except Exception as error:
                arms[mode] = json.loads((arm_output / 'summary.json').read_text()) if (arm_output / 'summary.json').exists() else {}
                arms[mode]['dispatch_error'] = f'{type(error).__name__}: {error}'
                atomic_json(output / f'{mode}-dispatch-error.json', {'error_type':type(error).__name__,'message':str(error)})
        # Merge new immutable records after both agents have finished. Each arm
        # previously read only its isolated store, never the other arm's output.
        combined = output / 'record-store'
        clone_store(initial_store, combined)
        for mode in plan['arm_order']:
            for name in commit_names(output / 'stores' / mode):
                if not (combined / 'commits' / name).exists():
                    shutil.copytree(output / 'stores' / mode / 'commits' / name, combined / 'commits' / name, copy_function=os.link)
        record_store = Store(combined)
        prior_test = snapshot['test_case_refs']['validation']
        case_record = make_record(project_id='balancing-cube', id=plan['study_id']+'.fresh-confirmation', kind='test_case', revision='1',
            actor={'type':'automation','id':'workflow-study-verifier'}, product_node='cube.verification',
            data={'stage':'validation','purpose':'development','source_snapshot_ref':snapshot['source_snapshot_ref'],
                  'partition':audit_snapshot['plan']['validation'], 'screening':snapshot['contract']['screening'],
                  'predeclared_plan_digest':digest(plan),'not_exposed_to_proposer':True,'physical_verified':False},
            links=[{'type':'derive','target':prior_test}])
        record_store.import_records([case_record])
        audits = {}
        for mode, summary in arms.items():
            selected_file = output / mode / 'validation/compiled.json'
            if summary.get('iterations_completed') != 10 or not selected_file.exists():
                audits[mode] = {'state':'not_run','reason':'ten measured iterations and a frozen selected candidate required'}
                continue
            selected = json.loads(selected_file.read_text())
            # Reuse the saved K exactly; only the verifier's seed partition changes.
            audit_adapter = BalancingCubeAdapter(audit_snapshot)
            selected['input_digest'] = digest({'config':selected['config'],'controller':selected['controller'], 'snapshot_digest':audit_adapter.frozen_digest})
            audit_dir = output / 'fresh-audit' / mode
            atomic_json(audit_dir / 'compiled.json', selected)
            audited = audit_adapter.rollout(selected, stage='validation', require_gpu=True, deadline=time.monotonic()+1800)
            atomic_json(audit_dir / 'result.json', audited)
            audits[mode] = {k:v for k,v in audited.items() if k!='records'}
            artifact_root = output
            artifact_path = (audit_dir / 'result.json').relative_to(output).as_posix()
            raw = (audit_dir / 'result.json').read_bytes()
            record = make_record(project_id='balancing-cube', id=plan['study_id']+'.fresh.'+mode,kind='simulation_run',revision='1',
                actor={'type':'automation','id':'workflow-study-verifier'},product_node='cube.verification',
                data={**audits[mode],'arm':mode,'saved_controller_digest':digest(selected['controller']),
                      'original_selected_controller_digest':digest(json.loads(selected_file.read_text())['controller']),
                      'source_run_id':summary['run_id'],'candidate_ref':summary['validation'].get('candidate_ref'),
                      'physical_verified':False},
                links=[{'type':'verify','target':{'id':case_record['id'],'revision':'1'},'scope':'fresh-seed numerical development evidence only'}],
                artifacts=[{'path':artifact_path,'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw)}])
            record_store.import_records([record],artifacts_root=artifact_root)
        final_check = record_store.check('balancing-cube')
        results = {'study_id':plan['study_id'],'state':'completed' if all(a.get('iterations_completed')==10 for a in arms.values()) and len(arms)==2 and final_check['ok'] else 'inconclusive',
                   'arms':arms,'fresh_audit':audits,'model_weights_updated':False,'physical_verified':False,
                   'onepiece_check':{k:v for k,v in final_check.items() if k!='warnings'},
                   'comparison_scope':'One paired pilot; equal budget ceilings, actual token use and candidate counts reported; no causal significance claim',
                   'finished_at':datetime.now(timezone.utc).isoformat()}
        atomic_json(output / 'study-results.json', results)
        atomic_json(output / 'status.json', {'state':results['state'],'completed_arms':list(arms)})
        atomic_json(output / 'initial-commit-ids.json', ids)
        return results
    finally:
        sampler.terminate()
        sampler.wait(timeout=15)
        shutdown_workers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = run(args.manifest,args.output)
    print(json.dumps({'study_id':result['study_id'],'state':result['state'],'rounds':{k:v.get('iterations_completed')for k,v in result['arms'].items()}}))
    if result['state']!='completed':
        raise SystemExit(2)


if __name__=='__main__':
    main()
