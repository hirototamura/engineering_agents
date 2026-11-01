"""Install stable user commands pointing to a versioned engineering checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex


def install(repo, workspace, binary_dir):
    repo,workspace,binary_dir=map(lambda p:Path(p).expanduser().resolve(),(repo,workspace,binary_dir))
    receipt_path=binary_dir/'.ea-engineering-launchers.json'
    previous=json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    generated={}
    for name,target in [('ea-engineering','deploy/eng-agents-008/bin/ea-engineering'),
                        ('engineering-hermes','deploy/eng-agents-008/hermes-engineering.sh')]:
        text=('#!/usr/bin/env bash\nset -euo pipefail\n'
              'if [[ -z "${EA_ENGINEERING_REPO:-}" ]]; then export EA_ENGINEERING_REPO='+shlex.quote(str(repo))+'; fi\n'
              'if [[ -z "${EA_WORKSPACE:-}" ]]; then export EA_WORKSPACE='+shlex.quote(str(workspace))+'; fi\n'
              'exec bash "$EA_ENGINEERING_REPO/'+target+'" "$@"\n')
        path=binary_dir/name
        if path.is_symlink():raise FileExistsError('Launcher destination is a symlink')
        if path.exists() and path.read_text()!=text:
            actual=hashlib.sha256(path.read_bytes()).hexdigest()
            if previous.get('hashes',{}).get(name)!=actual:raise FileExistsError('Existing launcher was not installed here or has human edits: '+name)
        generated[name]=text
    binary_dir.mkdir(parents=True,exist_ok=True)
    for name,text in generated.items():
        path=binary_dir/name;temporary=path.with_suffix('.ea-tmp')
        temporary.write_text(text);temporary.chmod(0o755);temporary.replace(path)
    receipt={'repository':str(repo),'workspace':str(workspace),'hashes':{n:hashlib.sha256(t.encode()).hexdigest() for n,t in generated.items()}}
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--workspace',type=Path,required=True);p.add_argument('--bin-dir',type=Path,required=True)
    a=p.parse_args();print(json.dumps(install(a.repo,a.workspace,a.bin_dir),indent=2))
