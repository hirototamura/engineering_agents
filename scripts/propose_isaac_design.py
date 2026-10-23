"""Feed measured Isaac evidence to the existing bounded Engineering Agents proposer."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core.llm.vllm import VllmClient
from scenario.balancing_cube.loop import _proposal
from scenario.balancing_cube.adapter import BalancingCubeAdapter
from scenario.balancing_cube.design import MECHANICAL_BOUNDS, CONTROL_BOUNDS

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('campaign',type=Path);parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--history',type=Path,action='append',default=[],help='Prior measured comparison JSON; repeat to retain bounded design history')
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
manifest=json.loads((args.campaign/'manifest.json').read_text())
payload=json.loads((Path(manifest['input'])/'input.json').read_text());snapshot=payload['snapshot']
stats=json.loads((args.campaign/'statistics.json').read_text())
p=payload['compiled']['config']['physics']
family=payload['compiled']['proposal']['family']
if family=='reference':
    matches=[name for name,spec in snapshot['families'].items() if np.isclose(spec['torque_cap_nm'],p['motor_torque_limit_nm']) and np.isclose(spec['no_load_speed_rad_s'],payload['compiled']['config']['actuation']['no_load_speed_rad_s'])]
    if len(matches)!=1:raise ValueError('Cannot resolve reference motor family uniquely')
    family=matches[0]
spec=snapshot['families'][family]
mass=p['wheel_mass_kg']-spec['rotor_mass_kg_assumption'];side=p['cube_side_m'];radius=p['wheel_radius_m']
parameters={'side_m':side,'print_mass_ref_kg':(p['frame_mass_kg']-3*(spec['total_motor_mass_kg_assumption']-spec['rotor_mass_kg_assumption'])-spec['other_fixed_mass_kg_assumption'])/(side/.18)**3,
    'wheel_mass_kg':mass,'wheel_radius_ratio':radius/side,
    'inner_radius_ratio':math.sqrt(2*(p['wheel_axial_inertia_kg_m2']-spec['rotor_axial_inertia_kg_m2_assumption'])/(mass*radius*radius)-1),
    'wheel_thickness_m':p['wheel_thickness_m']}
prompt={'stage':'PI','task':'Propose one mechanical architecture change after the measured eight-corner PhysX campaign.',
    'instruction':'Return one JSON proposal. Change mechanics only. Keep control omitted so the saved controller is identical. Prefer one mechanical dimension. Use one registered family and exactly the six listed mechanical parameters. Do not change wheel mounting, requirements, sensors, controller, gates, initial conditions, timestep or evaluation. You propose; deterministic screening decides. Include a falsifiable hypothesis and cite measured evidence. PhysX/MuJoCo agreement is inconclusive; do not claim a validated or physical improvement.',
    'proposal_schema':{'id':'string','family':list(snapshot['families']),'parameters':list(MECHANICAL_BOUNDS),'hypothesis':'string'},
    'mechanical_bounds':{k:[max(v[0],snapshot['design_bounds'].get(k,v)[0]),min(v[1],snapshot['design_bounds'].get(k,v)[1])] for k,v in MECHANICAL_BOUNDS.items()},
    'control_bounds_unchanged':CONTROL_BOUNDS,'families':snapshot['families'],
    'comparison_design':{'family':family,'parameters':parameters,'mount':p['wheel_mount_side']},
    'prior_measured_history':[{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'data':json.loads(path.read_text())} for path in args.history],
    'measured_statistics':stats,'requirements':snapshot['requirements'],'mission':snapshot['mission'],
    'source_snapshot_ref':snapshot['source_snapshot_ref'],
    'evidence_sha256':hashlib.sha256((args.campaign/'statistics.json').read_bytes()).hexdigest()}
(args.output/'prompt.json').write_text(json.dumps(prompt,indent=2)+'\n')
os.environ['EA_LLM_TRACE_DIR']=str((args.output/'model-traces').resolve())
client=VllmClient(base_url='http://127.0.0.1:8016/v1',model='qwen3.8-27b-q4-k-m',
    temperature=.3,max_tokens=4096,think=False,api_timeout=300)
os.environ['VLLM_MAX_MODEL_LEN']='65536'
text=json.dumps(prompt,ensure_ascii=False,separators=(',',':'))
if len(text)>(65536-4096-256)*3:raise ValueError('Prompt exceeds conservative context bound; refusing truncation')
proposal=_proposal(client,text,deadline=time.monotonic()+330)
(args.output/'proposal.json').write_text(json.dumps(proposal,indent=2)+'\n')
if proposal.get('control'): raise ValueError('This experiment requires the exact saved controller')
if proposal.get('family')==family and all(np.isclose(proposal.get('parameters',{}).get(k,float('nan')),v,rtol=1e-8,atol=1e-12) for k,v in parameters.items()):
    raise ValueError('No meaningful mechanical parameter change; round-trip floating-point differences are not an architecture proposal')
compiled=BalancingCubeAdapter(snapshot).compile(proposal)
if compiled['controller']!=payload['compiled']['controller']:raise ValueError('Controller changed')
if compiled['input_digest']==payload['compiled']['input_digest']:raise ValueError('Duplicate design')
(args.output/'compiled.json').write_text(json.dumps(compiled,indent=2)+'\n')
print(json.dumps(proposal,indent=2))
