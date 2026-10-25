"""Project-independent continuous-time SISO models and state-feedback synthesis."""
import numpy as np
from scipy import signal
from .common import number, require_units


def state_space(data):
    require_units(data)
    system = data['system']
    A, B, C, D = (np.asarray(system[k], dtype=float) for k in ('A', 'B', 'C', 'D'))
    n = len(A)
    if not 1 <= n <= 12 or A.shape != (n, n) or B.shape != (n, 1) or C.shape != (1, n) or D.shape != (1, 1):
        raise ValueError('Supply a 1..12 state continuous-time SISO realization')
    if not all(np.all(np.isfinite(v)) for v in (A, B, C, D)):
        raise ValueError('State matrices shall be finite')
    if len(system.get('state_units', [])) != n or not all(isinstance(u, str) and u for u in system['state_units']):
        raise ValueError('Supply one SI unit for each state')
    if not all(isinstance(system.get(k), str) and system[k] for k in ('input_unit', 'output_unit', 'model_scope')):
        raise ValueError('Supply input/output units and model_scope')
    return system, A, B, C, D


def encode_poles(poles):
    return [{'real': float(p.real), 'imag': float(p.imag)} for p in np.asarray(poles, dtype=complex)]


def transfer_function(data):
    system, A, B, C, D = state_space(data)
    denominator = np.poly(A)
    numerator = float(D[0,0])*denominator
    # C adj(sI-A) B, via the characteristic-polynomial recurrence.
    # Avoid subtraction of nearly equal characteristic polynomials: that loses
    # small but physical feedthrough/input coefficients in some ss2tf algorithms.
    adjugate_coefficient = np.eye(len(A))
    for i in range(len(A)):
        numerator[i+1] += float((C@adjugate_coefficient@B)[0,0])
        adjugate_coefficient = A@adjugate_coefficient+denominator[i+1]*np.eye(len(A))
    # Remove exact leading zeros only: small physical coefficients are meaningful.
    numerator = np.trim_zeros(numerator, 'f')
    if not len(numerator):
        numerator = np.array([0.])
    return {'system': system, 'transfer_function': {'numerator': numerator.tolist(),
            'denominator': denominator.tolist(), 'input_unit': system['input_unit'], 'output_unit': system['output_unit']},
            'state_poles_per_s': encode_poles(np.linalg.eigvals(A)),
            'model_scope': system['model_scope'], 'assumptions': data.get('assumptions', []),
            'limitations': ['Continuous-time SISO LTI realization supplied by the caller; no measured-data identification or automatic nonlinear linearization.',
                            'Zero initial state is assumed for the transfer function. No pole-zero cancellation is performed; retain state poles for internal stability.']}


def frequency_response(data):
    require_units(data)
    tf = data['transfer_function']
    num, den = (np.asarray(tf[k], dtype=float) for k in ('numerator', 'denominator'))
    if any(v.ndim != 1 or not len(v) or not np.all(np.isfinite(v)) for v in (num, den)) or den[0] == 0:
        raise ValueError('Transfer coefficients shall be finite descending-power arrays with nonzero leading denominator')
    if len(num) > len(den) or max(len(num), len(den)) > 13:
        raise ValueError('Supply a proper transfer function of order at most twelve')
    for key in ('input_unit', 'output_unit'):
        if not isinstance(tf.get(key), str) or not tf[key]:
            raise ValueError('Transfer input/output units are required')
    omega = np.array([number(w, 'omega_rad_s', positive=True) for w in data['omega_rad_s']])
    if not 2 <= len(omega) <= 10000 or np.any(np.diff(omega) <= 0):
        raise ValueError('Supply 2..10000 strictly increasing positive angular frequencies')
    with np.errstate(divide='ignore', invalid='ignore'):
        _, response = signal.freqs(num, den, worN=omega)
    if not np.all(np.isfinite(response)) or np.any(abs(response) == 0):
        raise ValueError('Frequency grid hits a singular or zero response; dB/phase would be undefined')
    return {'omega_rad_s': omega.tolist(), 'real': response.real.tolist(), 'imag': response.imag.tolist(),
            'magnitude_db': (20*np.log10(abs(response))).tolist(),
            'phase_deg': np.rad2deg(np.unwrap(np.angle(response))).tolist(),
            'magnitude_reference': f"1 {tf['output_unit']}/{tf['input_unit']}",
            'phase_convention': 'principal phase at lowest supplied frequency, unwrapped along increasing frequency',
            'limitations': ['Frequency response alone does not establish feedback stability or physical model accuracy.']}


def feedback(data):
    system, A, B, C, D = state_space(data)
    targets = []
    for value in data['desired_poles_per_s']:
        pole = complex(number(value['real'], 'pole real'), number(value.get('imag', 0), 'pole imag')) if isinstance(value, dict) else complex(number(value, 'pole'))
        if pole.real >= 0:
            raise ValueError('This design skill requires strictly left-half-plane target poles')
        targets.append(pole)
    if len(targets) != len(A):
        raise ValueError('One target pole per state is required')
    controllability = np.hstack([np.linalg.matrix_power(A, i) @ B for i in range(len(A))])
    if np.linalg.matrix_rank(controllability) != len(A):
        raise ValueError('State-space realization is not controllable')
    K = np.real_if_close(signal.place_poles(A, B, targets).gain_matrix)
    if np.iscomplexobj(K):
        raise ValueError('Target poles shall admit real gains (complex pairs shall be conjugate)')
    dt = number(data['control_period_s'], 'control_period_s', positive=True)
    Ad, Bd, _, _, _ = signal.cont2discrete((A, B, C, D), dt)
    closed, sampled = np.linalg.eigvals(A-B@K), np.linalg.eigvals(Ad-Bd@K)
    return {'K': K.tolist(), 'feedback_convention': 'u = -K x; full-state feedback',
            'gain_units': [f"{system['input_unit']}/({unit})" for unit in system['state_units']],
            'target_poles_per_s': encode_poles(targets), 'closed_loop_poles_per_s': encode_poles(closed),
            'sampled_closed_loop_poles': encode_poles(sampled), 'control_period_s': dt,
            'continuous_stable': bool(np.all(closed.real < 0)), 'sampled_stable': bool(np.all(abs(sampled) < 1)),
            'limitations': ['Full state is assumed available. Estimation error, actuator limits, delay and robustness are not included.',
                            'A continuous gain is assessed under zero-order-held sampling; production gains are not changed.']}
