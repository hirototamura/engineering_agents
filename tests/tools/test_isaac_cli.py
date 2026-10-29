"""CLI routing can be qualified without an Isaac installation or allocated GPU."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from types import SimpleNamespace

from typer.testing import CliRunner
from tools.cli.main import app

runner = CliRunner()


def test_five_commands_and_lazy_runtime_imports():
    result = runner.invoke(app, ['isaac', '--help'])
    assert result.exit_code == 0
    for command in ['prepare', 'run', 'analyze', 'plot', 'propose']:
        assert command in result.stdout
    code = """
import sys
from tools.cli.main import app
for name in ['environment.isaac.batch', 'environment.isaac.pilot', 'environment.isaac.convert', 'environment.isaac.audit', 'scenario.balancing_cube.isaac_proposal']:
    __import__(name)
assert not any(name in sys.modules for name in ['torch','warp','isaacsim','isaaclab','pxr'])
"""
    subprocess.run([sys.executable, '-c', code], check=True,
                   env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[2]/'src')})


def test_operation_help_does_not_load_optional_physics():
    for args in [['prepare','export'], ['run','campaign'], ['analyze'], ['plot'], ['propose']]:
        result = runner.invoke(app, ['isaac', *args, '--help'])
        assert result.exit_code == 0, result.output
        assert 'usage:' in result.output

    code = """
import importlib.abc
import sys

class BlockScipy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'scipy' or fullname.startswith('scipy.'):
            raise ModuleNotFoundError('SciPy is intentionally unavailable')

sys.meta_path.insert(0, BlockScipy())
from typer.testing import CliRunner
from tools.cli.main import app
from environment.isaac.conditions import trial_plan
assert len(trial_plan(8)['cases']) == 8
for args in [['prepare', 'export'], ['run', 'campaign'], ['analyze'], ['plot'], ['propose']]:
    result = CliRunner().invoke(app, ['isaac', *args, '--help'])
    assert result.exit_code == 0, (args, result.exception, result.output)
    assert 'usage:' in result.output
"""
    subprocess.run([sys.executable, '-c', code], check=True,
                   env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[2]/'src')})


def test_runtime_dispatch_keeps_python_path_arguments_and_failure(monkeypatch):
    calls=[]
    monkeypatch.setattr('tools.isaac.workflow.subprocess.call', lambda command: calls.append(command) or 7)
    result=runner.invoke(app,['isaac','run','batch','input with spaces','--python','/venv link/python', '--cases','cases.json','--output','new'])
    assert result.exit_code == 7
    assert calls == [['/venv link/python','-m','environment.isaac.batch','input with spaces','--cases','cases.json','--output','new']]
    assert runner.invoke(app,['isaac','run','campaign','input']).exit_code == 2


def test_campaign_launches_packaged_worker_and_records_hashes(tmp_path, monkeypatch):
    pytest.importorskip("scipy")
    from scenario.balancing_cube import isaac_campaign as campaign
    source=tmp_path/'input';source.mkdir();(source/'usd').mkdir()
    (source/'usd/cube.usd').write_text('fixture')
    (source/'cube.xml').write_text('<mujoco/>')
    (source/'input.json').write_text(json.dumps({'mjcf_sha256':hashlib.sha256((source/'cube.xml').read_bytes()).hexdigest()}))
    calls=[]
    def popen(command, **kwargs):
        calls.append((command,kwargs))
        return SimpleNamespace(poll=lambda:0, returncode=0, wait=lambda **kw:0)
    monkeypatch.setattr(campaign.subprocess,'check_output',lambda *a,**kw:'0, GPU-fixture, 0\n')
    monkeypatch.setattr(campaign.subprocess,'Popen',popen)
    output=tmp_path/'campaign'
    campaign.main([str(source),'--python',str(tmp_path/'venv/python'),'--output',str(output),'--gpus','0','--count','8'])
    manifest=json.loads((output/'manifest.json').read_text())
    assert manifest['status']=='completed'
    assert calls[0][0][1:3]==['-m','environment.isaac.batch']
    assert calls[0][1]['env']['CUDA_VISIBLE_DEVICES']=='GPU-fixture'
    assert manifest['worker_source_key']=='batch.py'
    assert manifest['source_hashes']['batch.py']==hashlib.sha256((output/'sources/batch.py').read_bytes()).hexdigest()


def test_trial_plot_uses_recorded_stop(tmp_path):
    import numpy as np
    from tools.isaac.plots import main
    rows=[{'corner':f'{i:03b}','status':'lost_balance'} for i in range(8)]
    (tmp_path/'result.json').write_text(json.dumps({'summaries':rows}))
    np.savez(tmp_path/'telemetry.npz',time_s=np.arange(3),values=np.zeros((3,8,3)),end_tick=np.ones(8,dtype=int))
    main([str(tmp_path)])
    assert (tmp_path/'tilt-traces.png').read_bytes().startswith(b'\x89PNG')
