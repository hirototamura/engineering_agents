"""Bounded live Hermes/Qwen acceptance; final prose is not an execution oracle."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shlex
import time

SKILLS={'gnc':'cube-gnc-loop-analysis','mechanical':'cube-mechanical-mass-uncertainty',
        'electrical':'cube-electrical-wheel-power','systems':'cube-systems-evidence-assessment'}


def run(repo, output, *, workspace=None, timeout=240, only=None):
    repo, output=Path(repo).resolve(),Path(output).resolve()
    workspace=Path(workspace).resolve() if workspace else repo.parent
    if output.exists():raise FileExistsError('Use a new acceptance output directory')
    output.mkdir(parents=True)
    reports=[]
    for discipline,skill in SKILLS.items():
        if only and discipline!=only:continue
        task_dir=output/discipline;task_dir.mkdir()
        destination=task_dir/'analysis'
        input_path=repo/'skills/engineering'/skill/'examples/input.json'
        analysis_command=shlex.join(['ea-engineering','run',discipline,'--input',str(input_path),'--output',str(destination)])
        query=(f'Use the {skill} skill in Hermes. Load its instructions with skill_view. '
               f'From {repo}, execute `{analysis_command}` using the trusted Engineering Agents analysis calculator on {input_path}. '
               f'Write the analysis to the NEW directory {destination}. Do not replace the input or calculator. '
               'Read the result and receipt, then explain the main engineering conclusion and limitations. '
               'This is a validation exercise using assumed/synthetic data. Do not change requirements, baselines, '
               'source code, devices, services, or other files. Use terminal tools; do not provide only a proposed command.')
        (task_dir/'query.txt').write_text(query)
        env=os.environ.copy();env.update(EA_ENGINEERING_REPO=str(repo),EA_WORKSPACE=str(workspace))
        command=['bash',str(repo/'deploy/eng-agents-008/hermes-engineering.sh'),'chat','--oneshot',
                 '--max-turns','8','--reasoning','low','--run-budget',str(timeout),'-t','terminal,skills',
                 '--format','stream-json','--query-file',str(task_dir/'query.txt')]
        started=time.monotonic()
        try:
            with (task_dir/'hermes.jsonl').open('w') as stdout, (task_dir/'stderr.txt').open('w') as stderr:
                completed=subprocess.run(command,env=env,stdout=stdout,stderr=stderr,timeout=timeout+30)
            code=completed.returncode
        except subprocess.TimeoutExpired:
            code=124
        receipt_path=destination/'receipt.json'
        receipt=json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        result_path=destination/'result.json'
        result=json.loads(result_path.read_text()) if result_path.exists() else {}
        transcript=(task_dir/'hermes.jsonl').read_text()
        # Require observable tool activity and trusted, hash-matched artifacts.
        tool_activity='tool' in transcript and 'terminal' in transcript
        input_ok=receipt.get('input_sha256')==hashlib.sha256(input_path.read_bytes()).hexdigest()
        result_ok=result_path.exists() and receipt.get('result_sha256')==hashlib.sha256(result_path.read_bytes()).hexdigest()
        expected=(bool(result.get('sampled_stable')) if discipline=='gnc' else
                  result.get('system') is None and bool(result.get('known_parts')) if discipline=='mechanical' else
                  result.get('feasible') is False and bool(result.get('modes')) if discipline=='electrical' else
                  result.get('requirements',[{}])[0].get('state')=='inconclusive')
        reports.append({'discipline':discipline,'skill':skill,'process_exit':code,
                        'elapsed_seconds':time.monotonic()-started,'tool_activity_observed':tool_activity,
                        'input_hash_matches':input_ok,'result_hash_matches':result_ok,
                        'expected_behavior':bool(expected),'status':receipt.get('status','not_run'),
                        'accepted':code==0 and tool_activity and input_ok and result_ok and bool(expected) and receipt.get('status')=='completed'})
        (output/'acceptance.json').write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),
            'model_profile':'qwen3.8-27b-q4-k-m','tests':reports,'passed':all(r['accepted'] for r in reports)},indent=2)+'\n')
    return all(r['accepted'] for r in reports)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--workspace',type=Path)
    parser.add_argument('--timeout',type=int,default=240);parser.add_argument('--only',choices=list(SKILLS))
    args=parser.parse_args()
    raise SystemExit(0 if run(args.repo,args.output,workspace=args.workspace,timeout=args.timeout,only=args.only) else 1)
