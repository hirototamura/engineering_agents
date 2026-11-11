"""Independent numerical oracles for leaf control analysis skills."""
import copy
import numpy as np
import pytest
from environment.engineering_analysis import linear

BASE = {'units':'SI','data_basis':'synthetic_validation','system':{
    'A':[[0,1],[-2,-3]],'B':[[0],[1]],'C':[[1,0]],'D':[[0]],
    'state_units':['m','m/s'],'input_unit':'N','output_unit':'m','model_scope':'mass spring damper'}}


def test_transfer_function_matches_closed_form_and_retains_state_basis():
    result = linear.transfer_function(BASE)
    tf = result['transfer_function']
    for s in (0,1,2j,-.5+3j):
        assert np.polyval(tf['numerator'],s)/np.polyval(tf['denominator'],s) == pytest.approx(1/(s*s+3*s+2))
    assert result['system'] == BASE['system']


def test_feedthrough_zero_transfer_and_small_real_coefficients():
    system = {'A':[[-2]],'B':[[3]],'C':[[4]],'D':[[.5]],
              'state_units':['V'],'input_unit':'A','output_unit':'V','model_scope':'first order electrical model'}
    data = {**BASE,'system':system}
    tf = linear.transfer_function(data)['transfer_function']
    assert tf['numerator'] == pytest.approx([.5,13])
    assert tf['denominator'] == pytest.approx([1,2])
    zero = linear.transfer_function({**data,'system':{**system,'C':[[0]],'D':[[0]]}})
    assert zero['transfer_function']['numerator'] == [0]
    tiny = linear.transfer_function({**data,'system':{**system,'C':[[0]],'D':[[1e-16]]}})
    assert tiny['transfer_function']['numerator'][0] == 1e-16


def test_transfer_polynomial_matches_independent_resolvent_for_three_states():
    A=np.array([[-1,.2,0],[.3,-2,.1],[0,.4,-3]])
    B=np.array([[1],[2],[3]]);C=np.array([[.4,.5,.6]])
    system={'A':A.tolist(),'B':B.tolist(),'C':C.tolist(),'D':[[.05]],
            'state_units':['V']*3,'input_unit':'A','output_unit':'V','model_scope':'three state test model'}
    result=linear.transfer_function({**BASE,'system':system})['transfer_function']
    for s in (.2j,1+2j,10j):
        expected=(C@np.linalg.solve(s*np.eye(3)-A,B))[0,0]+.05
        actual=np.polyval(result['numerator'],s)/np.polyval(result['denominator'],s)
        assert actual==pytest.approx(expected,rel=1e-12)


@pytest.mark.parametrize('change',[{'B':[[1,2]]},{'state_units':[]},{'A':[[float('nan'),1],[-2,-3]]}])
def test_transfer_model_shape_and_unit_contracts(change):
    with pytest.raises(ValueError):
        linear.transfer_function({**BASE,'system':{**BASE['system'],**change}})


def test_frequency_response_against_independent_rc_solution():
    omega = np.logspace(-2,2,31)
    result = linear.frequency_response({**BASE,'transfer_function':{
        'numerator':[1],'denominator':[2,1],'input_unit':'V','output_unit':'V'},'omega_rad_s':omega.tolist()})
    exact = 1/(1+2j*omega)
    assert result['real'] == pytest.approx(exact.real)
    assert result['imag'] == pytest.approx(exact.imag)
    assert result['magnitude_db'] == pytest.approx(-10*np.log10(1+4*omega*omega))
    assert result['phase_deg'] == pytest.approx(-np.rad2deg(np.arctan(2*omega)))


@pytest.mark.parametrize('tf,grid',[
    ({'numerator':[0],'denominator':[1,1]},[1,2]),
    ({'numerator':[1],'denominator':[1,0,1]},[1,2]),
    ({'numerator':[1],'denominator':[1,1]},[2,1]),
    ({'numerator':[1],'denominator':[1,1]},[0,1]),
    ({'numerator':[1,1],'denominator':[1]},[1,2])])
def test_frequency_response_rejects_undefined_or_invalid_results(tf,grid):
    with pytest.raises(ValueError):
        linear.frequency_response({**BASE,'transfer_function':{**tf,'input_unit':'V','output_unit':'V'},'omega_rad_s':grid})


def test_feedback_against_independent_second_order_gain_formula():
    result = linear.feedback({**BASE,'desired_poles_per_s':[-4,-6],'control_period_s':.015})
    assert result['K'][0] == pytest.approx([24-2,10-3])
    assert sorted(p['real'] for p in result['closed_loop_poles_per_s']) == pytest.approx([-6,-4])
    assert result['sampled_stable']
    complex_pair = linear.feedback({**BASE,'desired_poles_per_s':[{'real':-2,'imag':3},{'real':-2,'imag':-3}],'control_period_s':.01})
    assert complex_pair['K'][0] == pytest.approx([13-2,4-3])


def test_first_order_gain_and_sampling_have_independent_closed_forms():
    system = {'A':[[-2]],'B':[[3]],'C':[[4]],'D':[[0]],
              'state_units':['V'],'input_unit':'A','output_unit':'V','model_scope':'first order model'}
    result = linear.feedback({**BASE,'system':system,'desired_poles_per_s':[-8],'control_period_s':.2})
    assert result['K'][0] == pytest.approx([2])
    expected = np.exp(-.4)-3*(1-np.exp(-.4))/2*2
    assert result['sampled_closed_loop_poles'][0]['real'] == pytest.approx(expected)
    fast = linear.feedback({**BASE,'desired_poles_per_s':[-400,-600],'control_period_s':.015})
    assert fast['continuous_stable'] and not fast['sampled_stable']


def test_uncontrollable_and_nonconjugate_designs_rejected():
    with pytest.raises(ValueError,match='controllable'):
        linear.feedback({**BASE,'system':{**BASE['system'],'B':[[0],[0]]},'desired_poles_per_s':[-4,-6],'control_period_s':.01})
    with pytest.raises(ValueError):
        linear.feedback({**BASE,'desired_poles_per_s':[{'real':-2,'imag':3},-4],'control_period_s':.01})
