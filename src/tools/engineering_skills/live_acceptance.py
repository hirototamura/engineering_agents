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


def inspect_tool_trace(text, discipline, skill):
    events=[]
    for line in text.splitlines():
        try:
            value=json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value,dict):events.append(value)
    calls={e.get('tool_call_id'):e for e in events if e.get('type') in ('tool_use','tool_call')}
    loaded=executed=False
    for event in events:
        if event.get('type')!='tool_result' or event.get('is_error'):
            continue
        call=calls.get(event.get('tool_call_id'),{})
        args=call.get('input',call.get('arguments',{}))
        if isinstance(args,str):
            try:args=json.loads(args)
            except json.JSONDecodeError:continue
        output=event.get('output',{})
        if isinstance(output,str):
            try:output=json.loads(output)
            except json.JSONDecodeError:continue
        if call.get('name')=='skill_view' and args.get('name')==skill and output.get('success') is True:
            loaded=True
        if call.get('name')=='terminal' and output.get('exit_code')==0:
            try:tokens=shlex.split(args.get('command',''))
            except ValueError:continue
            for i,token in enumerate(tokens):
                if Path(token).name=='ea-engineering' and tokens[i+1:i+3]==['run',discipline]:executed=True
    return {'skill_loaded':loaded,'calculator_tool_succeeded':executed}


def acceptance_report(reports, expected_count):
    complete=len(reports)==expected_count
    return {'created_at':datetime.now(timezone.utc).isoformat(),
            'model_profile':'qwen3.8-27b-q4-k-m','expected_case_count':expected_count,
            'completed_case_count':len(reports),'complete':complete,'tests':reports,
            'passed':complete and all(r['accepted'] for r in reports)}


def run(repo, output, *, workspace=None, timeout=240, only=None):
    if only is not None and only not in SKILLS:
        raise ValueError('Unknown discipline')
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
               'Read summary.json and receipt.json with cat (no Python heredocs or ad hoc scripts), then explain the main engineering conclusion and limitations. '
               'This is a validation exercise using assumed/synthetic data. Do not change requirements, baselines, '
               'source code, devices, services, or other files. Use terminal tools; do not provide only a proposed command.')
        (task_dir/'query.txt').write_text(query)
        env=os.environ.copy();env.update(EA_ENGINEERING_REPO=str(repo),EA_WORKSPACE=str(workspace))
        command=['bash',str(repo/'deploy/eng-agents-008/hermes-engineering.sh'),'chat','--oneshot',
                 '--max-turns','12','--reasoning','low','-t','terminal,skills',
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
        observed=inspect_tool_trace(transcript,discipline,skill)
        tool_activity=observed['skill_loaded'] and observed['calculator_tool_succeeded']
        input_ok=receipt.get('input_sha256')==hashlib.sha256(input_path.read_bytes()).hexdigest()
        result_ok=result_path.exists() and receipt.get('result_sha256')==hashlib.sha256(result_path.read_bytes()).hexdigest()
        source_ok=receipt.get('calculator_sha256')==hashlib.sha256((repo/'src/environment/engineering_analysis'/(discipline+'.py')).read_bytes()).hexdigest()
        expected=(bool(result.get('sampled_stable')) if discipline=='gnc' else
                  result.get('system') is None and bool(result.get('known_parts')) if discipline=='mechanical' else
                  result.get('feasible') is False and bool(result.get('modes')) if discipline=='electrical' else
                  (result.get('requirements') or [{}])[0].get('state')=='inconclusive')
        reports.append({'discipline':discipline,'skill':skill,'process_exit':code,
                        'elapsed_seconds':time.monotonic()-started,'tool_activity_observed':tool_activity,
                        'input_hash_matches':input_ok,'result_hash_matches':result_ok,'calculator_hash_matches':source_ok,**observed,
                        'expected_behavior':bool(expected),'status':receipt.get('status','not_run'),
                        'accepted':code==0 and tool_activity and input_ok and result_ok and source_ok and bool(expected) and receipt.get('status')=='completed'})
        (output/'acceptance.json').write_text(json.dumps(acceptance_report(reports,1 if only else len(SKILLS)),indent=2)+'\n')
    return acceptance_report(reports,1 if only else len(SKILLS))['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--workspace',type=Path)
    parser.add_argument('--timeout',type=int,default=240);parser.add_argument('--only',choices=list(SKILLS))
    args=parser.parse_args()
    raise SystemExit(0 if run(args.repo,args.output,workspace=args.workspace,timeout=args.timeout,only=args.only) else 1)
