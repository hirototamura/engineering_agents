import json
from pathlib import Path

import pytest

pytest.importorskip('mujoco')

from integrations.one_piece.mechanical_bridge import atomic_json
from scenario.balancing_cube.adapter import BalancingCubeAdapter
from scenario.balancing_cube.design import digest
from tools.replay_cube_cpu_reference import replay


def reference_files(tmp_path):
    source=tmp_path/'source'
    model=json.loads((Path(__file__).parents[1]/'fixtures/balancing_cube_snapshot.json').read_text())
    adapter=BalancingCubeAdapter(model)
    compiled=adapter.compile({'id':'saved','family':'reference','parameters':{},'hypothesis':'Saved numerical reference'})
    result=adapter.rollout(compiled,stage='validation')
    for name,value in [('compiled',compiled),('result',result),('frozen-snapshot',model),('environment',adapter.reset())]:
        atomic_json(source/(name+'.json'),value)
    return source,compiled


def test_cpu_replay_uses_saved_gains_without_designing_a_controller(tmp_path,monkeypatch):
    source,compiled=reference_files(tmp_path)
    def forbidden(*args,**kwargs):
        raise AssertionError('Replay cannot design a controller')
    monkeypatch.setattr('scenario.balancing_cube.design.compile_controller',forbidden)
    monkeypatch.setattr('environment.mujoco.contact.Regulator',forbidden)
    result=replay(source,tmp_path/'replay')
    assert result['state']=='passed'
    assert result['source_controller_digest']==digest(compiled['controller'])
    assert result['saved_controller_preserved'] is True
    assert result['numeric_gpu_verified'] is False
    assert result['physical_verified'] is False
    assert all(c['local_backend']['accelerated'] is False for c in result['cases'])
    with pytest.raises(ValueError,match='immutable'):
        replay(source,tmp_path/'replay')


@pytest.mark.parametrize('name',['compiled','environment'])
def test_cpu_replay_rejects_changed_gains_or_evaluator(tmp_path,name):
    source,compiled=reference_files(tmp_path)
    path=source/(name+'.json');data=json.loads(path.read_text())
    if name=='compiled':
        data['controller']['K'][0][0]+=1
    else:
        data['code_digests']['model.py']='different'
    atomic_json(path,data)
    with pytest.raises(ValueError,match='differs'):
        replay(source,tmp_path/'replay')
    assert not (tmp_path/'replay').exists()
