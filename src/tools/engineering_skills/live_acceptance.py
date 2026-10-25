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
from environment.engineering_analysis.catalog import resolve,implementation

SKILLS={'gnc':'cube-gnc-loop-analysis','mechanical':'mass-property-uncertainty',
        'electrical':'actuator-duty-cycle-analysis','systems':'requirement-evidence-assessment',
        'bode':'bode-diagram-analysis'}


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
                if Path(token).name=='ea-engineering' and len(tokens)>i+2 and tokens[i+1]=='run' and tokens[i+2] in (discipline,skill):executed=True
    return {'skill_loaded':loaded,'calculator_tool_succeeded':executed}


def acceptance_report(reports, expected_count):
    complete=len(reports)==expected_count
    return {'created_at':datetime.now(timezone.utc).isoformat(),
            'model_profile':'qwen3.8-27b-q4-k-m','expected_case_count':expected_count,
            'completed_case_count':len(reports),'complete':complete,'tests':reports,
            'passed':complete and all(r['accepted'] for r in reports)}


def verify_lineage(output):
    """Check retained primary/child artifacts against current executable contracts."""
    output=Path(output).resolve()
    receipt=json.loads((output/'receipt.json').read_text())
    skill=resolve(receipt['skill'])
    module=implementation(skill)
    if receipt['status']!='completed' or receipt['contract']!=skill.contract():
        raise ValueError('Incomplete or stale skill contract')
    if receipt['calculator_sha256']!=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest():
        raise ValueError('Calculator source changed')
    from environment.engineering_analysis import common,catalog
    for key,path in [('common_guards_sha256',Path(common.__file__)),
                     ('catalog_sha256',Path(catalog.__file__)),('runner_sha256',Path(__file__).with_name('runner.py'))]:
        if receipt[key]!=hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('Shared tool or contract source changed')
    result=json.loads((output/'result.json').read_text())
    if result.get('skill')!=skill.name or result.get('output_type')!=skill.output_type or result.get('schema_version')!=1:
        raise ValueError('Primary output type differs from its contract')
    for relative,digest in receipt['artifacts'].items():
        path=(output/relative).resolve()
        if not path.is_relative_to(output) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Artifact hash mismatch or path escape')
    if receipt['result_sha256']!=hashlib.sha256((output/'result.json').read_bytes()).hexdigest():
        raise ValueError('Primary result hash mismatch')
    if {r['skill'] for r in receipt['dependencies']}!=set(skill.requires):
        raise ValueError('Declared dependency set differs from execution')
    count=1
    for ref in receipt['dependencies']:
        result_path=(output/ref['result_path']).resolve()
        if not result_path.is_relative_to(output):
            raise ValueError('Dependency path escapes parent output')
        child=json.loads((result_path.parent/'receipt.json').read_text())
        if child['skill']!=ref['skill'] or ref['input_sha256']!=child['input_sha256'] or ref['result_sha256']!=child['result_sha256']:
            raise ValueError('Dependency binding mismatch')
        if ref['receipt_sha256']!=hashlib.sha256((result_path.parent/'receipt.json').read_bytes()).hexdigest():
            raise ValueError('Dependency receipt hash mismatch')
        count+=verify_lineage(result_path.parent)
    return count


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
        analysis_command=shlex.join(['ea-engineering','run',skill,'--input',str(input_path),'--output',str(destination)])
        query=(f'Use the {skill} skill in Hermes. Load its instructions with skill_view. '
               'This is an explicitly requested fresh qualification run. Execute the supplied calculator command after loading the skill; '
               'workspace surveys, old-run discovery and inspection of this harness query/log files are unnecessary for this task. '
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
        source_ok=receipt.get('calculator_sha256')==hashlib.sha256(Path(implementation(resolve(skill)).__file__).read_bytes()).hexdigest()
        try:
            lineage_count=verify_lineage(destination)
        except (OSError,ValueError,KeyError,TypeError):
            lineage_count=0
        expected=(result.get('state')=='pass' and bool(result.get('criteria')) if discipline=='bode' else
                  bool(result.get('sampled_stable')) if discipline=='gnc' else
                  result.get('system') is None and bool(result.get('known_parts')) if discipline=='mechanical' else
                  result.get('feasible') is False and bool(result.get('modes')) if discipline=='electrical' else
                  (result.get('requirements') or [{}])[0].get('state')=='inconclusive')
        reports.append({'discipline':discipline,'skill':skill,'process_exit':code,
                        'elapsed_seconds':time.monotonic()-started,'tool_activity_observed':tool_activity,
                        'input_hash_matches':input_ok,'result_hash_matches':result_ok,'calculator_hash_matches':source_ok,**observed,
                        'expected_behavior':bool(expected),'status':receipt.get('status','not_run'),
                        'qualified_lineage_nodes':lineage_count,
                        'accepted':code==0 and tool_activity and input_ok and result_ok and source_ok and bool(expected) and lineage_count>0 and receipt.get('status')=='completed'})
        (output/'acceptance.json').write_text(json.dumps(acceptance_report(reports,1 if only else len(SKILLS)),indent=2)+'\n')
    return acceptance_report(reports,1 if only else len(SKILLS))['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--workspace',type=Path)
    parser.add_argument('--timeout',type=int,default=240);parser.add_argument('--only',choices=list(SKILLS))
    args=parser.parse_args()
    raise SystemExit(0 if run(args.repo,args.output,workspace=args.workspace,timeout=args.timeout,only=args.only) else 1)
