"""Missing or tampered evidence must never become a success-rate denominator."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('isaac_stats',Path(__file__).resolve().parents[2]/'scripts/summarize_isaac_campaign.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def save(path,value):
    path.write_text(json.dumps(value));return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def campaign(tmp_path):
    source=tmp_path/'input';source.mkdir();root=tmp_path/'run';root.mkdir();shard=root/'shard-0';shard.mkdir()
    case={'id':'one','corner':'000','seed':5,'duration_s':6.0}
    contract={'screening':{'criteria':[{'metric':'peak_tilt_deg','operator':'<=','limit':5}], 'required_duration_s':6}}
    digest=save(source/'input.json',{'compiled':{'input_digest':'frozen'},'snapshot':{'contract':contract}})
    plan=save(root/'plan.json',{'cases':[case]})
    save(root/'manifest.json',{'status':'completed','input':str(source),'input_sha256':digest,'plan_sha256':plan,
        'source_hashes':{'run_cube_batch_isaac.py':'source'},
        'shards':[{'rank':0,'gpu_uuid':'gpu','cases_sha256':'cases','trial_count':1}]})
    row={**case,'status':'completed','simulated_duration_s':6,'peak_tilt_deg':1,'final_1s_tilt_rms_deg':.1,
        'peak_wheel_rpm':200,'peak_slip_speed_m_s':.001,'peak_pivot_displacement_mm':.1}
    save(shard/'result.json',{'gpu_uuid':'gpu','cases_sha256':'cases','input_digest':'frozen','source_sha256':'source','trial_count':1,'summaries':[row]})
    return root


def test_complete_evidence_and_confidence_interval(campaign):
    statistics,rows=module.summarize(campaign)
    assert statistics['trial_count']==1 and rows[0]['screening_passed']
    assert statistics['corners']['000']['wilson_95_ci'][0]<1
    assert statistics['physical_verified'] is False


@pytest.mark.parametrize('mutation',['missing','duplicate','changed_seed','wrong_gpu','changed_source'])
def test_corrupt_shard_is_rejected(campaign,mutation):
    path=campaign/'shard-0/result.json';value=json.loads(path.read_text())
    if mutation=='missing':value['summaries']=[]
    if mutation=='duplicate':value['summaries']*=2
    if mutation=='changed_seed':value['summaries'][0]['seed']=6
    if mutation=='wrong_gpu':value['gpu_uuid']='other'
    if mutation=='changed_source':value['source_sha256']='other'
    save(path,value)
    with pytest.raises(ValueError):module.summarize(campaign)
