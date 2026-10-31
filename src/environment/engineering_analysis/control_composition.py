"""Compositions bind a model to qualified frequency and feedback calculations."""
import numpy as np
from .common import number


def bode_jobs(data, results):
    yield 'plant', 'transfer-function-derivation', data
    frequencies = list(data['omega_rad_s'])
    for criterion in data.get('criteria', []):
        if criterion['metric'] not in ('magnitude_db', 'phase_deg') or criterion['operator'] not in ('<=', '>='):
            raise ValueError('Bode criteria use magnitude_db/phase_deg and <=/>= at an explicit omega_rad_s')
        frequencies.append(number(criterion['omega_rad_s'], 'criterion frequency', positive=True))
        number(criterion['value'], 'criterion threshold')
    frequencies = sorted(set(frequencies))
    yield 'response', 'frequency-response-calculation', {
        'units': data['units'], 'data_basis': data['data_basis'],
        'transfer_function': results['plant']['transfer_function'], 'omega_rad_s': frequencies}


def bode(data, results):
    response = results['response']
    rows = []
    for criterion in data.get('criteria', []):
        index = response['omega_rad_s'].index(float(criterion['omega_rad_s']))
        value = response[criterion['metric']][index]
        passed = value <= criterion['value'] if criterion['operator'] == '<=' else value >= criterion['value']
        rows.append({**criterion, 'actual': value, 'state': 'pass' if passed else 'fail'})
    stable = all(p['real'] < 0 for p in results['plant']['state_poles_per_s'])
    return {'bode': response, 'criteria': rows, 'state': 'fail' if any(r['state']=='fail' for r in rows) else 'pass' if rows else 'unassessed',
            'internally_asymptotically_stable_plant': stable,
            'evaluation_scope': 'Only explicit frequency-point criteria; no criteria means unassessed.',
            'limitations': ['Frequency-point checks do not certify an entire band or feedback stability.',
                            'No classical gain/phase margin claim is made without a defined loop and stability assumptions.',
                            'Phase criteria use the response artifact phase convention. Model assumptions remain applicable.']}


def pole_jobs(data, results):
    yield 'plant', 'transfer-function-derivation', data
    # Reuse the exact state realization, not a newly canonicalized realization.
    yield 'feedback', 'state-feedback-gain-synthesis', {**data, 'system': results['plant']['system']}


def pole(data, results):
    result = dict(results['feedback'])
    result['state'] = 'pass' if result['continuous_stable'] and result['sampled_stable'] else 'fail'
    result['plant_transfer_function'] = results['plant']['transfer_function']
    return result
