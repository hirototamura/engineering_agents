"""Run a frozen, balanced eight-corner plan across explicitly allocated GPUs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from environment.isaac.conditions import trial_plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=24576)
    parser.add_argument('--seed', type=int, default=20261023)
    parser.add_argument('--gpus', default='0,1,2,3,4,5')
    parser.add_argument('--timeout', type=float, default=3600)
    args = parser.parse_args(argv)
    indices = [int(x) for x in args.gpus.split(',')]
    if len(set(indices)) != len(indices) or not indices or not set(indices) <= set(range(6)):
        raise ValueError('Only the user-allocated physical GPUs 0–5 are permitted')
    if args.count % (8*len(indices)):
        raise ValueError('Each GPU shard must contain equally many trials for all eight corners')
    plan = trial_plan(args.count, args.seed)
    payload=json.loads((args.input/'input.json').read_text())
    if hashlib.sha256((args.input/'cube.xml').read_bytes()).hexdigest()!=payload['mjcf_sha256']:
        raise ValueError('Exported MJCF changed')
    assets={str(p.relative_to(args.input)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (args.input/'usd').rglob('*') if p.is_file()}
    if not assets:raise ValueError('No converted USD asset')
    inventory = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,memory.used',
        '--format=csv,noheader,nounits'], text=True)
    devices = {int(a): (b.strip(), int(c)) for a,b,c in (line.split(',') for line in inventory.splitlines())}
    if any(devices[i][1] > 100 for i in indices):
        raise RuntimeError('An allocated GPU is occupied; refusing to overlap another workload')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    from environment.isaac import batch, conditions
    source = Path(batch.__file__)
    sources = args.output/'sources'; sources.mkdir()
    for path in [Path(__file__), source, Path(conditions.__file__)]:
        shutil.copy2(path, sources/path.name)
    manifest = {'input': str(args.input.resolve()), 'input_sha256': hashlib.sha256((args.input/'input.json').read_bytes()).hexdigest(),
        'plan_sha256': hashlib.sha256((args.output/'plan.json').read_bytes()).hexdigest(),
        'gpu_inventory_before': inventory, 'shards': [], 'physical_verified': False,'asset_hashes':assets,
        'worker_source_key': source.name,
        'worker_module': 'environment.isaac.batch',
        'source_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.iterdir()}}
    children = []
    started = time.monotonic()
    try:
        size = args.count//len(indices)
        for rank, index in enumerate(indices):
            cases = args.output/f'cases-{rank}.json'
            cases.write_text(json.dumps({'cases':plan['cases'][rank*size:(rank+1)*size]},indent=2)+'\n')
            output = args.output/f'shard-{rank}'
            log = (args.output/f'shard-{rank}.log').open('w')
            gpu = devices[index][0]
            env = {**os.environ, 'CUDA_VISIBLE_DEVICES':gpu, 'OMNI_KIT_ACCEPT_EULA':'YES', 'HEADLESS':'1'}
            # Preserve the venv entry path: resolving its symlink loses pyvenv.cfg.
            command = [str(args.python.absolute()), '-m', 'environment.isaac.batch', str(args.input.resolve()),
                '--cases', str(cases.resolve()), '--output', str(output.resolve())]
            process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
            children.append((process, log))
            manifest['shards'].append({'rank':rank,'gpu_index':index,'gpu_uuid':gpu,
                'trial_count':size,'cases_sha256':hashlib.sha256(cases.read_bytes()).hexdigest(),'command':command})
        (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        while any(p.poll() is None for p,_ in children):
            if time.monotonic()-started > args.timeout:
                raise TimeoutError('Campaign exceeded wall-clock bound')
            if any(p.poll() not in (None,0) for p,_ in children):
                raise RuntimeError('A GPU shard failed; campaign is incomplete')
            sample = subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.used,utilization.gpu',
                '--format=csv,noheader,nounits'],text=True)
            with (args.output/'gpu-samples.jsonl').open('a') as monitor:
                monitor.write(json.dumps({'elapsed_s':time.monotonic()-started,'inventory':sample})+'\n')
            time.sleep(2)
        if any(p.returncode != 0 for p,_ in children):
            raise RuntimeError('A GPU shard failed')
        if any(hashlib.sha256((args.input/path).read_bytes()).hexdigest()!=value for path,value in assets.items()):
            raise RuntimeError('Converted USD assets changed during the campaign')
        manifest.update(status='completed',wall_time_s=time.monotonic()-started)
    except BaseException as error:
        manifest.update(status='failed',error=str(error),wall_time_s=time.monotonic()-started)
        raise
    finally:
        for p,log in children:
            if p.poll() is None: p.terminate()
        for p,log in children:
            try: p.wait(timeout=15)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
            log.close()
        (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'status':manifest['status'],'trials':args.count,'wall_time_s':manifest['wall_time_s']}))


if __name__ == '__main__':
    main()
