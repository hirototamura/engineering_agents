"""Replay selected native CPU cases with saved inputs, without controller design."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

from integrations.one_piece.mechanical_bridge import atomic_json
from scenario.balancing_cube.adapter import BalancingCubeAdapter
from scenario.balancing_cube.design import digest, trial_matrix
from scenario.balancing_cube.evaluation import paired_metrics, screening


def replay(source, output, *, condition_id=None, seed=None):
    import numpy as np
    from environment.mujoco.backend import native_rollout
    source, output = Path(source).resolve(), Path(output).resolve()
    names = ('compiled.json', 'result.json', 'frozen-snapshot.json', 'environment.json')
    hashes = {name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in names}
    if (source/'source-sha256.json').exists():
        if json.loads((source/'source-sha256.json').read_text()) != hashes:
            raise ValueError('Source hash mismatch')
    compiled, reference, snapshot, environment = [json.loads((source/name).read_text()) for name in names]
    adapter = BalancingCubeAdapter(snapshot)
    if adapter.reset()['code_digests'] != environment['code_digests']:
        raise ValueError('Local evaluator code differs from the recorded reference')
    expected = digest({'config':compiled['config'], 'controller':compiled['controller'],
                       'snapshot_digest':adapter.frozen_digest})
    saved_controller = digest(compiled['controller'])
    if (compiled['input_digest'] != expected or reference['input_digest'] != expected
            or reference['controller_digest'] != saved_controller):
        raise ValueError('Saved configuration or controller digest differs from the reference')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Replay output is immutable; choose an empty directory')
    records = {(r['domain_id'], r['condition_id'], r['seed']):r for r in reference['records']}
    trials = trial_matrix(compiled['config'], snapshot, compiled['id'], reference['stage'])
    if len(records) != len(reference['records']) or set(records) != {t['key'] for t in trials}:
        raise ValueError('Reference case identities differ from the frozen trial matrix')
    selected = [t for t in trials if (condition_id is None or t['key'][1] == condition_id)
                and (seed is None or t['key'][2] == seed)]
    if not selected:
        raise ValueError('No reference cases match the requested condition and seed')
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    for index, trial in enumerate(selected, 1):
        original = records[trial['key']]
        local = native_rollout(trial['config'], trial['case'], compiled['controller'])
        if local['metadata']['mujoco_version'] != original['backend']['mujoco_version']:
            raise ValueError('Native MuJoCo version differs from the reference')
        check = paired_metrics(original, local, snapshot['contract'],
            control_period_s=trial['config']['physics']['control_period_s'])
        gates = screening(local['summary'], snapshot['contract'])
        same_gates = [g['passed'] for g in gates] == [g['passed'] for g in original['screening']]
        old_t = np.array([r['time_s'] for r in original['rows']])
        new_t = np.array([r['time_s'] for r in local['rows']])
        end = min(old_t[-1], new_t[-1])
        mask = (old_t >= max(old_t[0],new_t[0])) & (old_t <= end)
        errors = np.array([r['tilt_total_deg'] for r in original['rows']])[mask] - np.interp(
            old_t[mask], new_t, [r['tilt_total_deg'] for r in local['rows']])
        entry = {'key':list(trial['key']), 'comparison_kind':'native CPU to native CPU',
            'passed':check['passed'] and same_gates, 'agreement_checks':check,
            'same_gate_decisions':same_gates, 'overlap_interval_s':[float(old_t[mask][0]),float(end)],
            'full_overlap_tilt_rmse_deg':float(np.sqrt(np.mean(errors**2))),
            'full_overlap_max_abs_tilt_error_deg':float(np.abs(errors).max()),
            'reference_summary':original['summary'], 'local_summary':local['summary'],
            'physics_timestep_s':trial['config']['physics']['timestep_s'],
            'control_period_s':trial['config']['physics']['control_period_s'],
            'local_backend':local['metadata'], 'artifact':f'case-{index:03d}.json'}
        atomic_json(output/entry['artifact'],local)
        cases.append(entry)
    if digest(compiled['controller']) != saved_controller:
        raise ValueError('Saved controller changed during replay')
    result = {'state':'passed' if all(c['passed'] for c in cases) else 'inconclusive',
        'scope':'CPU platform reproduction with the existing numerical agreement tolerances; reproduced gate failures remain failures.',
        'source_candidate_id':reference['candidate_id'], 'source_input_digest':expected,
        'source_controller_digest':saved_controller, 'source_hashes':hashes,
        'saved_controller_preserved':True, 'evaluator_code_digests_match':True,
        'numeric_gpu_verified':False, 'physical_verified':False,
        'half_step_adjudication_performed':False, 'cases':cases,
        'local_runtime':{'python':sys.version,'system':platform.system(),'machine':platform.machine(),'numpy':np.__version__}}
    atomic_json(output/'report.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--condition-id')
    parser.add_argument('--seed',type=int)
    args=parser.parse_args()
    result=replay(args.source,args.output,condition_id=args.condition_id,seed=args.seed)
    print(json.dumps({'state':result['state'],'cases':len(result['cases']),
                      'saved_controller_preserved':result['saved_controller_preserved']}))
    if result['state'] != 'passed':
        raise SystemExit(2)


if __name__=='__main__':
    main()
