import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from tools import workflow_study_report as report


def test_report_languages_share_data_and_keep_incomplete_status(tmp_path, monkeypatch):
    data={'manifest':{'predeclared_at':'2026-10-17T06:00:00+00:00'},
          'results':{'state':'inconclusive','arms':{m:{'iterations_completed':0}for m in report.MODES},'fresh_audit':{m:{'state':'not_run'}for m in report.MODES}},
          'arms':{m:{'rounds':[],'candidates':[],'cases':[],'compiled':None}for m in report.MODES},'sources':[]}
    monkeypatch.setattr(report,'extract',lambda root:data)
    outputs=report.build(tmp_path)
    payloads=[]
    for lang,path in zip(['en','ja'],outputs):
        text=path.read_text()
        assert f'<html lang="{lang}">'in text
        assert '@@'not in text
        assert not re.search(r'<script\b[^>]*src=',text)
        payloads.append(json.loads(re.search(r'<script id="study-data" type="application/json">(.*?)</script>',text,re.S)[1]))
        assert 'incomplete' in text
        assert 'physical' in text
    assert payloads==[data,data]
    node = shutil.which('node')
    if node:
        # Check generated code, not a separately maintained JS example.
        for path in outputs:
            script=re.findall(r'<script>(.*?)</script>',path.read_text(),re.S)[0]
            code=tmp_path/'generated.js'; code.write_text(script)
            subprocess.run([node,'--check',str(code)],check=True,capture_output=True,text=True)


def test_extract_aligns_exact_cases_and_counts_cached_rounds(tmp_path):
    def write(path,data):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))
    write(tmp_path/'study-manifest.json',{'predeclared_at':'2026-10-17T06:00:00+00:00'})
    summary={'arms':{mode:{'rounds':[{'round':1,'candidate_ids':['old']}]}
                     for mode in report.MODES}}
    write(tmp_path/'study-results.json',summary)
    def case(seed):
        return {'domain_id':'nominal','condition_id':'release','seed':seed,'summary':{},
                'paired_metrics':{'state':'verified'},'screening':[{'passed':True}],
                'frames':[{'time_s':0,'position_m':[0,0,0],'quaternion_wxyz':[1,0,0,0],
                           'wheel_angle_rad':[0,0,0],'tilt_total_deg':0,
                           'wheel_x_rpm':1,'wheel_y_rpm':-2,'wheel_z_rpm':3}]}
    for mode in report.MODES:
        write(tmp_path/mode/'round-01/workflow/round-summary.json',{'calls':{}})
        write(tmp_path/mode/'round-01/proposal.json',{})
        write(tmp_path/mode/'round-01/workflow/critic.result.json',{'final_answer':{}})
        write(tmp_path/mode/'candidates/candidate-001/result.json',{
            'candidate_id':'old','round':0,'matrix_cell':'starting_design','score':.9,
            'all_screening_passed':True,'numeric_gpu_verified':True,'screening_pass_fraction':1,
            'input_digest':'input','controller_digest':'controller','records':[case(1)]})
        write(tmp_path/'fresh-audit'/mode/'result.json',{'records':[case(i) for i in ([1,2] if mode=='multi_agent' else [2,1])]})
        write(tmp_path/'fresh-audit'/mode/'compiled.json',{})
    (tmp_path/'gpu-telemetry.jsonl').write_text('\n'.join(json.dumps(s) for s in [
        {'timestamp':'t0','devices':[{'id':0,'name':'GPU','utilization_percent':20,'memory_used_mib':100}]},
        {'timestamp':'t1','devices':[{'id':0,'name':'GPU','utilization_percent':80,'memory_used_mib':200}]}]))
    write(tmp_path/'multi_agent/round-02/rejected.json',{'status':'rejected','error':'Invalid JSON'})
    write(tmp_path/'multi_agent/round-02/workflow/mechanical.result.json',{
        'role':'mechanical','completion_token_cap':4096,'usage':{'completion_tokens':4096},
        'final_answer':'UNSTRUCTURED_CONTENT_NOT_FOR_REPORT'})
    data=report.extract(tmp_path)
    assert data['arms']['multi_agent']['cases']==data['arms']['single_agent']['cases']
    assert data['arms']['multi_agent']['rounds'][0]['new_configurations']==0
    assert data['arms']['multi_agent']['rounds'][0]['reused_evaluations']==1
    assert data['gpu_usage']['devices'][0]['mean_sample_utilization_percent']==50
    assert data['gpu_usage']['devices'][0]['peak_memory_used_mib']==200
    assert data['arms']['multi_agent']['cases'][0]['frames'][0]['max_abs_wheel_rpm']==3
    failed=data['arms']['multi_agent']['failures'][0]
    assert failed['call_metadata'][0]['structured_object'] is False
    assert failed['call_metadata'][0]['usage']['completion_tokens']==4096
    assert 'UNSTRUCTURED_CONTENT_NOT_FOR_REPORT' not in json.dumps(data)
    write(tmp_path/'fresh-audit/single_agent/result.json',{'records':[case(2),case(3)]})
    with pytest.raises(ValueError,match='case identities differ'):
        report.extract(tmp_path)
