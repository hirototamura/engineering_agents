"""Workflow contracts, real simulation feedback, and budget isolation."""
import copy
import json
from pathlib import Path
import time

import pytest

from core.llm.base import LLMGeneration
from scenario.balancing_cube.workflow import DesignWorkflow, INITIAL, ROLE_CAPS, validate_workflow, project_context


class WorkflowFake:
    api_timeout = 30
    def __init__(self):
        self.prompts = []

    def count_prompt_tokens(self, prompt):
        return len(prompt) // 4 + 100

    def generate_result(self, text):
        data = json.loads(text)
        self.prompts.append(data)
        role = data['step']
        if role == 'optimizer':
            result = {k: copy.deepcopy(v) for k, v in INITIAL.items() if k != 'revision'}
            result.update(routing='sequential_cross_review', focus='speed_headroom', rationale='Measured feedback motivates a paired cross-review.')
        elif role == 'critic':
            result = {'preferred': 'control', 'concerns': ['Check delayed observation'], 'required_checks': ['screening'], 'evidence_refs': []}
        else:
            number = data['context'].get('policy', {}).get('revision', 1)
            proposal = {'id': 'workflow-probe', 'family': 'dc_rs385', 'parameters': {
                'side_m': .18, 'print_mass_ref_kg': .12, 'wheel_mass_kg': .05,
                'wheel_radius_ratio': .30, 'inner_radius_ratio': .80, 'wheel_thickness_m': .006},
                'control': {'tilt_q_scale': .5 + number * .1, 'rate_q_scale': 1.,
                            'momentum_q_scale': 1., 'yaw_rate_gain_nm_s': .03},
                'hypothesis': 'Test a bounded controller change against saved numerical evidence.'}
            result = proposal if role == 'coordinator' else {'proposal': proposal, 'prediction': {'metric': 'final_1s_tilt_rms_deg', 'direction': 'lower'},
                         'falsification': 'No measured improvement', 'evidence_refs': ['fixture@1'], 'assumptions': ['unmeasured model']}
        return LLMGeneration(text=json.dumps(result), thinking='PRIVATE REASONING SHALL NOT BE SAVED',
            usage={'prompt_tokens': self.count_prompt_tokens(text), 'completion_tokens': 100})


def test_multi_agent_blind_context_then_measured_workflow_evolution(tmp_path):
    client, workflow = WorkflowFake(), DesignWorkflow()
    deadline = time.monotonic() + 30
    proposal = workflow.propose(client, {'policy': {'revision': 1}}, tmp_path, deadline=deadline)
    specialist = [p for p in client.prompts if p['step'] in {'mechanical', 'control'}]
    assert all(p['inputs'] == {} for p in specialist)
    assert proposal['family'] == 'dc_rs385'
    report = workflow.observe(client, {'cells': [{'score': .7}], 'context_reread': True}, tmp_path, deadline=deadline)
    assert report['workflow_out']['routing'] == 'sequential_cross_review'
    assert report['workflow_out']['revision'] == 2
    workflow.propose(client, {'policy': {'revision': 2}}, tmp_path / 'next', deadline=deadline)
    later = [p for p in client.prompts[5:] if p['step'] in {'mechanical', 'control'}]
    assert len(later[1]['inputs']['earlier_drafts']) == 1
    for path in tmp_path.rglob('*.json'):
        assert 'PRIVATE REASONING SHALL NOT BE SAVED' not in path.read_text()


def test_single_agent_preserves_shared_history_and_equal_caps(tmp_path):
    client, workflow = WorkflowFake(), DesignWorkflow('single_agent')
    deadline = time.monotonic() + 30
    workflow.propose(client, {}, tmp_path, deadline=deadline)
    assert {p['role'] for p in client.prompts} == {'single_designer'}
    assert client.prompts[1]['inputs']['earlier_drafts']
    result = workflow.observe(client, {'score': .8, 'context_reread': True}, tmp_path, deadline=deadline)
    assert result['completion_token_cap'] == sum(ROLE_CAPS.values())
    assert result['actual_completion_tokens'] == 500
    assert workflow.summary()['calls_recorded'] == 5
    assert result['workflow_out']['routing'] == 'sequential_cross_review'


def test_workflow_cannot_edit_verifier_and_budget_rejects_before_inference(tmp_path):
    unsafe = {k: v for k, v in INITIAL.items() if k != 'revision'}
    unsafe['physics_timestep_s'] = .01
    with pytest.raises(ValueError):
        validate_workflow(unsafe, INITIAL)
    client, workflow = WorkflowFake(), DesignWorkflow(prompt_token_cap=1000)
    with pytest.raises(ValueError, match='prompt-token budget'):
        workflow.propose(client, {'large': 'a' * 10000}, tmp_path, deadline=time.monotonic() + 30)
    assert client.prompts == []


def test_context_projection_preserves_obligations_values_and_campaign_summary():
    requirement = {'id':'R-HOLD','revision':'draft-1','kind':'requirement','links':[],
        'data':{'statement':'The Cube shall hold its vertex position for at least 30 s.',
                'acceptance_criteria':{'value':30,'unit':'s'},'approval_state':'pending_human_review'}}
    parameter = {'id':'D-SIDE','revision':'1','kind':'parameter','links':[],
        'data':{'name':'Side length','value':.18,'unit':'m','bounds':[.14,.22],'origin':'assumed'}}
    campaign = {'id':'summary','revision':'1','kind':'campaign_summary','links':[],
        'data':{'prior46':{'pass':31,'fail':9,'inconclusive':6}}}
    source={'context_data':{'records':[requirement,parameter,campaign],
        'frozen_execution':{'screening':{'required_duration_s':6}}}}
    before=copy.deepcopy(source);projected=project_context(source)
    assert source==before
    assert projected['context_data']['records'][0]==requirement
    assert projected['context_data']['records'][2]==campaign
    for key in ('value','unit','bounds','origin'):
        assert projected['context_data']['records'][1]['data'][key]==parameter['data'][key]
    assert projected['context_data']['frozen_execution']==source['context_data']['frozen_execution']


def test_two_rounds_use_real_cpu_rollouts_and_reread_onepiece(tmp_path):
    pytest.importorskip('mujoco')
    pytest.importorskip('onepiece')
    from scenario.balancing_cube.loop import run_design_loop
    from scenario.balancing_cube.memory import EngineeringMemory
    from tests.scenario.test_balancing_cube import ssot_bridge
    bridge = ssot_bridge(tmp_path)
    workflow, client = DesignWorkflow(), WorkflowFake()
    result = run_design_loop(snapshot=bridge.load_snapshot(), output_dir=tmp_path / 'run',
        llm_client=client, rounds=2, max_candidates=12, stagnation_rounds=2,
        bridge=bridge, memory=lambda: EngineeringMemory(tmp_path / 'run/memory/episodes.jsonl'), workflow=workflow)
    assert result['iterations_completed'] == 2
    assert result['proposal_workflow']['calls_recorded'] == 10
    assert all(r['context_reread'] for r in result['rounds'])
    policies = [r for r in bridge.store.records(kinds=['design_policy']) if '.workflow.' in r['id']]
    assert len(policies) == 2
    assert bridge.store.check()['ok']
    for number in [1, 2]:
        context = json.loads((tmp_path / f'run/round-{number:02d}/workflow/measurement-context.json').read_text())
        assert any(r['kind'] == 'simulation_run' for r in context['records'])
    assert all(not r['data'].get('physical_verified') for r in policies)
