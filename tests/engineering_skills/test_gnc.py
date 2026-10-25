import copy
import numpy as np
import pytest
from environment.engineering_analysis.gnc import analyze

BASE = dict(units='SI', data_basis='synthetic_validation', mass_kg=1., com_height_m=.1,
            pivot_inertia_kg_m2=.02, damping_N_m_s_rad=.005, desired_poles_per_s=[-4., -6.],
            body_torque_limit_N_m=1., duration_s=2., control_period_s=.015)


def test_equations_poles_and_independent_gain_formula():
    r = analyze(BASE)
    assert sorted(r['closed_loop_poles_per_s']) == pytest.approx([-6, -4])
    kp = .02*24 + 9.80665*.1
    kd = .02*10-.005
    assert r['K'][0] == pytest.approx([kp, kd])
    assert r['open_loop_unstable']
    assert max(r['open_loop_poles_per_s']) > 0
    w = np.array(r['bode']['omega_rad_s'])
    independently = 1/np.sqrt((-.02*w*w-.980665)**2+(.005*w)**2)
    assert r['bode']['magnitude_db'] == pytest.approx(20*np.log10(independently))
    assert r['sampled_stable']


def test_small_angle_nonlinear_response_matches_linear_and_torque_is_limited():
    r = analyze({**BASE, 'initial_tilt_rad': 1e-4})
    trace = np.array(r['trace'])
    assert max(abs(trace[:, 1]-trace[:, 3])) < 1e-8
    assert abs(r['final_nonlinear_tilt_rad']) < 1e-5
    saturated = analyze({**BASE, 'body_torque_limit_N_m': .0001, 'duration_s': .2})
    assert saturated['saturated_samples'] > 0
    assert max(abs(np.array(saturated['trace'])[:, 5])) <= .0001


def test_continuous_poles_do_not_guarantee_sampled_stability():
    r = analyze({**BASE, 'desired_poles_per_s': [-400., -600.], 'duration_s': .015})
    assert not r['sampled_stable']


@pytest.mark.parametrize('change', [{'units':'mm'}, {'mass_kg':0}, {'desired_poles_per_s':[1.,-2.]}, {'initial_tilt_rad':1.}])
def test_invalid_inputs_rejected(change):
    with pytest.raises(ValueError):
        analyze({**BASE, **change})
