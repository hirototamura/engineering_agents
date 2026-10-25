"""Execute engineering calculations and retain inputs, hashes and plots."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import numpy as np

DISCIPLINES = ('gnc', 'mechanical', 'electrical', 'systems')


def digest_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def json_write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def verify_artifacts(data, root):
    for evidence in data.get('evidence', []):
        evidence['artifact_verified'] = False  # Never trust this field from an LLM.
        artifact = evidence.get('artifact', {})
        candidate = (root/artifact.get('path', '')).resolve()
        if not candidate.is_relative_to(root.resolve()):
            raise ValueError('Artifact escapes explicit artifact root')
        if candidate.is_file() and artifact.get('sha256'):
            evidence['artifact_verified'] = digest_bytes(candidate.read_bytes()) == artifact['sha256']


def verify_canonical_requirements(data, store_path):
    if data.get('data_basis') == 'synthetic_validation':
        return {'verified': False, 'reason': 'synthetic validation records; not canonical requirements'}
    if store_path is None:
        raise ValueError('Non-synthetic systems assessment requires --store One-Piece canonical storage')
    from onepiece import Store
    store = Store(store_path)
    checked = store.check('balancing-cube')
    if not checked['ok']:
        raise ValueError('One-Piece integrity check failed')
    index = {(r['id'], r['revision']): r for r in store.records('balancing-cube', ['requirement'])}
    for record in data['requirements']:
        if index.get((record['id'], record['revision'])) != record:
            raise ValueError('Requirement payload does not match its canonical One-Piece revision')
    return {'verified': True, 'store': str(Path(store_path).resolve()),
            'record_digests': [digest_bytes(canonical(r)) for r in data['requirements']],
            'store_implementation': Store.__module__,
            'store_implementation_sha256': digest_bytes(Path(inspect.getsourcefile(Store)).read_bytes())}


def plot_results(discipline, result, output):
    if discipline == 'systems':
        return
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    if discipline == 'gnc':
        fig, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
        b = result['bode']
        axes[0].semilogx(b['omega_rad_s'], b['magnitude_db'])
        axes[1].semilogx(b['omega_rad_s'], b['phase_deg'])
        for axis in axes:
            axis.axvline(result['nyquist_rad_s'], color='tab:red', linestyle='--', label='Sampling Nyquist')
            axis.grid(True, which='both', alpha=.25)
        axes[0].set_ylabel('Magnitude / dB (rad/N m)');axes[1].set_ylabel('Phase / deg');axes[1].set_xlabel('Angular frequency / rad s⁻¹')
        axes[0].set_title('Local tilt-axis plant — open-loop unstable');fig.tight_layout();fig.savefig(output/'bode.png', dpi=150);plt.close(fig)
        trace = np.array(result['trace']);fig, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
        axes[0].plot(trace[:, 0], trace[:, 1], label='Linear ZOH');axes[0].plot(trace[:, 0], trace[:, 3], '--', label='Nonlinear, saturated')
        axes[0].legend();axes[0].set_ylabel('Tilt / rad');axes[1].plot(trace[:, 0], trace[:, 5]);axes[1].set_ylabel('Body torque / N m');axes[1].set_xlabel('Time / s')
        fig.tight_layout();fig.savefig(output/'response.png', dpi=150);plt.close(fig)
        np.savetxt(output/'response.csv', trace, delimiter=',', header=','.join(result['trace_columns']), comments='')
    elif discipline == 'mechanical':
        u = result['uncertainty'];fig, axis = plt.subplots(figsize=(8, 4))
        low, high = np.array(u['q025'])[1:4], np.array(u['q975'])[1:4];mid = (low+high)/2
        axis.errorbar(['x', 'y', 'z'], mid*1000, yerr=np.array([mid-low, high-mid])*1000, fmt='o', capsize=6)
        axis.set_ylabel('Known-parts CoM / mm');axis.set_title('Bounded-input Monte Carlo: empirical central 95% range');fig.tight_layout();fig.savefig(output/'com_uncertainty.png', dpi=150);plt.close(fig)
    else:
        rows = result['modes'];fig, axes = plt.subplots(2, 1, figsize=(8, 6))
        names = [r['mode'] for r in rows];axes[0].bar(names, [r['battery_W_all_motors'] for r in rows]);axes[0].set_ylabel('Battery power / W')
        axes[1].bar(names, [r['end_winding_K']-273.15 for r in rows]);axes[1].set_ylabel('End winding / °C');fig.tight_layout();fig.savefig(output/'power_thermal.png', dpi=150);plt.close(fig)


def run(discipline, input_path, output, *, store=None, artifact_root=None):
    raw = Path(input_path).read_bytes()
    data = json.loads(raw)
    out = Path(output)
    if out.exists():
        raise FileExistsError('Use a new output directory; previous evidence is immutable')
    out.mkdir(parents=True)
    (out/'input.json').write_bytes(raw)
    started = time.monotonic()
    receipt = {'schema_version': 1, 'discipline': discipline, 'input_sha256': digest_bytes(raw),
               'started_at': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
               'data_basis': data.get('data_basis'), 'physical_verified': False, 'status': 'running',
               'numpy_version': np.__version__, 'runner_sha256': digest_bytes(Path(__file__).read_bytes())}
    try:
        receipt['source_revision'] = subprocess.check_output(['git', '-C', str(Path(__file__).resolve().parents[3]), 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        receipt['source_revision'] = None
    try:
        if discipline == 'systems':
            receipt['canonical_requirements'] = verify_canonical_requirements(data, store)
            verify_artifacts(data, Path(artifact_root) if artifact_root else Path(input_path).resolve().parent)
        module = importlib.import_module('environment.engineering_analysis.'+discipline)
        from environment.engineering_analysis import common
        receipt['calculator_sha256'] = digest_bytes(Path(module.__file__).read_bytes())
        receipt['common_guards_sha256'] = digest_bytes(Path(common.__file__).read_bytes())
        import scipy
        receipt['scipy_version'] = scipy.__version__
        result = module.analyze(data)
        json_write(out/'result.json', result)
        summary = {k: v for k, v in result.items() if k not in ('bode', 'trace', 'parts')}
        if 'parts' in result:
            summary['part_count'] = len(result['parts'])
        json_write(out/'summary.json', summary)
        plot_results(discipline, result, out)
        receipt['status'] = 'completed'
        receipt['result_sha256'] = digest_bytes((out/'result.json').read_bytes())
    except Exception as error:
        receipt.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        receipt['elapsed_seconds'] = time.monotonic()-started
        receipt['artifacts'] = {p.name: digest_bytes(p.read_bytes()) for p in out.iterdir() if p.is_file() and p.name != 'receipt.json'}
        json_write(out/'receipt.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('run');p.add_argument('discipline', choices=DISCIPLINES)
    p.add_argument('--input', required=True, type=Path);p.add_argument('--output', required=True, type=Path)
    p.add_argument('--store', type=Path);p.add_argument('--artifact-root', type=Path)
    args = parser.parse_args()
    try:
        result = run(args.discipline, args.input, args.output, store=args.store, artifact_root=args.artifact_root)
        print(json.dumps(result, indent=2))
    except Exception as error:
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        raise SystemExit(1)
