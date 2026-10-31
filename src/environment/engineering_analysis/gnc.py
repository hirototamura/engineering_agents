"""Single tilt-axis inverted-pendulum analysis, with body-torque input."""
import numpy as np
from scipy import signal
from scipy.integrate import solve_ivp
from .common import number, require_units


def analyze(data, dependencies=None):
    require_units(data)
    m = number(data['mass_kg'], 'mass_kg', positive=True)
    h = number(data['com_height_m'], 'com_height_m', positive=True)
    inertia = number(data['pivot_inertia_kg_m2'], 'pivot_inertia_kg_m2', positive=True)
    damping = number(data.get('damping_N_m_s_rad', 0), 'damping', nonnegative=True)
    g = number(data.get('gravity_m_s2', 9.80665), 'gravity', positive=True)
    dt = number(data.get('control_period_s', .015), 'control_period_s', positive=True)
    horizon = number(data.get('duration_s', 6), 'duration_s', positive=True)
    if horizon > 30 or horizon/dt > 20000:
        raise ValueError('Local diagnostic budget exceeded')
    poles = data['desired_poles_per_s']
    if len(poles) != 2 or any(number(p, 'desired pole') >= 0 for p in poles) or poles[0] == poles[1]:
        raise ValueError('Specify two distinct negative real poles')
    A = np.array([[0, 1], [m*g*h/inertia, -damping/inertia]])
    B = np.array([[0], [1/inertia]])
    if dependencies is None:
        from .catalog import calculate
        dependencies = {}
        for role, skill, value in jobs(data, dependencies):
            dependencies[role] = calculate(skill, value)
    K = np.array(dependencies['feedback']['K'])
    Ad, Bd, _, _, _ = signal.cont2discrete((A, B, np.eye(2), np.zeros((2, 1))), dt)
    sampled_poles = np.array([complex(p['real'], p['imag']) for p in dependencies['feedback']['sampled_closed_loop_poles']])
    limit = number(data['body_torque_limit_N_m'], 'body_torque_limit_N_m', positive=True)
    angle = number(data.get('initial_tilt_rad', .02), 'initial_tilt_rad')
    if abs(angle) > .25:
        raise ValueError('This small-angle diagnostic limits initial tilt to 0.25 rad')
    linear = np.array([angle, 0.])
    nonlinear = linear.copy()
    rows = []
    count = int(np.ceil(horizon/dt))
    saturated = 0
    for i in range(count):
        t = i*dt
        step = min(dt, horizon-t)
        command = float(-(K@nonlinear)[0])
        torque = float(np.clip(command, -limit, limit))
        saturated += abs(command) > limit
        rows.append([t, *linear, *nonlinear, torque])
        # Zero-order-held feedback; the nonlinear ODE has the same body-torque sign.
        nonlinear = solve_ivp(lambda _, x: [x[1], (m*g*h*np.sin(x[0])-damping*x[1]+torque)/inertia],
                              (0, step), nonlinear, rtol=1e-9, atol=1e-11).y[:, -1]
        if step != dt:
            As, Bs, _, _, _ = signal.cont2discrete((A, B, np.eye(2), np.zeros((2, 1))), step)
        else:
            As, Bs = Ad, Bd
        linear = As@linear+Bs[:, 0]*float(-(K@linear)[0])
    rows.append([horizon, *linear, *nonlinear, float(np.clip(-(K@nonlinear)[0], -limit, limit))])
    trace = np.array(rows)
    return {'model': 'one tilt axis, fixed pivot, body torque input, small-angle linearization',
            'input_sign': 'positive u is positive body torque; ideal reaction-wheel motor torque has opposite sign',
            'equation': 'J*theta_ddot + d*theta_dot - m*g*h*theta = u_body',
            'A': A.tolist(), 'B': B.tolist(), 'transfer_function': dependencies['plant']['transfer_function'],
            'open_loop_poles_per_s': np.real_if_close(np.linalg.eigvals(A)).tolist(), 'open_loop_unstable': True,
            'K': K.tolist(), 'closed_loop_poles_per_s': np.real_if_close(np.linalg.eigvals(A-B@K)).tolist(),
            'sampled_closed_loop_poles': [{'real': float(p.real), 'imag': float(p.imag)} for p in sampled_poles],
            'sampled_stable': bool(np.all(abs(sampled_poles) < 1)), 'control_period_s': dt,
            'nyquist_rad_s': float(np.pi/dt),
            'bode': dependencies['bode']['bode'], 'frequency_assessment': dependencies['bode']['state'],
            'trace_columns': ['time_s', 'linear_tilt_rad', 'linear_rate_rad_s', 'nonlinear_tilt_rad', 'nonlinear_rate_rad_s', 'body_torque_N_m'],
            'trace': trace.tolist(), 'saturated_samples': int(saturated),
            'final_nonlinear_tilt_rad': float(nonlinear[0]),
            'small_angle_scope_exceeded': bool(np.max(abs(trace[:, 3])) > .25),
            'limitations': ['Not a three-axis controller or estimator design.', 'Wheel-speed/momentum limits, contact slip, sensor dynamics and structural flexibility are excluded.',
                            'Continuous pole placement is checked separately under zero-order-held sampling.',
                            'No production gain or simulation configuration is changed.']}


def jobs(data, results):
    require_units(data)
    m = number(data['mass_kg'], 'mass_kg', positive=True)
    h = number(data['com_height_m'], 'com_height_m', positive=True)
    inertia = number(data['pivot_inertia_kg_m2'], 'pivot inertia', positive=True)
    damping = number(data.get('damping_N_m_s_rad',0), 'damping', nonnegative=True)
    g = number(data.get('gravity_m_s2',9.80665), 'gravity', positive=True)
    model = {'units':data['units'], 'data_basis':data['data_basis'],
        'system':{'A':[[0,1],[m*g*h/inertia,-damping/inertia]], 'B':[[0],[1/inertia]],
            'C':[[1,0]], 'D':[[0]], 'state_units':['rad','rad/s'], 'input_unit':'N*m', 'output_unit':'rad',
            'model_scope':'upright fixed-pivot single-axis cube linearization; positive body torque input'},
        'assumptions':['J theta_ddot + d theta_dot - m g h theta = u_body; ideal wheel motor torque has the opposite sign.']}
    yield 'plant', 'transfer-function-derivation', model
    yield 'bode', 'bode-diagram-analysis', {**model,'omega_rad_s':np.logspace(-1,3,401).tolist(),
        'criteria':data.get('frequency_criteria',[])}
    yield 'feedback', 'pole-placement-design', {**model,'desired_poles_per_s':data['desired_poles_per_s'],
        'control_period_s':data.get('control_period_s',.015)}
