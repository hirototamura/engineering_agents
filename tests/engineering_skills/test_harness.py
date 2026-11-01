import json
import os
from pathlib import Path
import subprocess
import sys
import yaml
from environment.engineering_analysis.catalog import SKILLS

REPO=Path(__file__).resolve().parents[2]


def test_hermes_wrapper_does_not_shadow_its_own_tools_package(tmp_path):
    workspace=tmp_path/'workspace with spaces';workspace.mkdir()
    binary=workspace/'.venv/bin';binary.mkdir(parents=True)
    (binary/'python').symlink_to(sys.executable)
    fake=tmp_path/'commands';fake.mkdir()
    (fake/'curl').write_text('#!/bin/sh\nexit 0\n');(fake/'curl').chmod(0o755)
    runtime=workspace/'.runtime/hermes-agent/.venv/bin';runtime.mkdir(parents=True)
    stub=runtime/'hermes'
    stub.write_text('#!/bin/sh\nexec "$EA_TEST_PYTHON" -c \'import os,json; print(json.dumps({k:os.environ.get(k) for k in ["PYTHONPATH","EA_ENGINEERING_REPO","HERMES_HOME","PATH"]}))\'\n')
    stub.chmod(0o755)
    env={**os.environ,'EA_WORKSPACE':str(workspace),'EA_ENGINEERING_REPO':str(REPO),
         'EA_TEST_PYTHON':sys.executable,'PYTHONPATH':'/a/colliding/python/tools',
         'PATH':str(fake)+os.pathsep+os.environ['PATH']}
    completed=subprocess.run(['bash',str(REPO/'deploy/eng-agents-008/hermes-engineering.sh'),'--help'],env=env,capture_output=True,text=True,check=True)
    result=json.loads(completed.stdout)
    assert result['PYTHONPATH'] is None
    assert result['EA_ENGINEERING_REPO']==str(REPO)
    assert str(REPO/'deploy/eng-agents-008/bin') in result['PATH'].split(os.pathsep)
    assert len(list((workspace/'.runtime/hermes-home/skills/engineering').glob('*/SKILL.md'))) == len(SKILLS)


def test_portable_catalog_frontmatter_and_validation_links():
    for path in (REPO/'skills/engineering').glob('*/SKILL.md'):
        front=path.read_text().split('---',2)[1]
        data=yaml.safe_load(front)
        assert data['name']==path.parent.name and len(data['description'])>25
        assert (path.parent/'references/validation.md').is_file()
        assert (path.parent/'examples/input.json').is_file()
