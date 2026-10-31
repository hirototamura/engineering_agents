"""Independent energy and thermal oracles for project-agnostic leaves."""
import math
import pytest
from environment.engineering_analysis import motor,thermal

MOTOR = {'units':'SI','data_basis':'synthetic_validation','motor_convention':'effective_dc',
    'torque_constant_N_m_A':.1,'back_emf_V_s_rad':.1,'winding_resistance_ohm':2,
    'bus_voltage_V':12,'driver_efficiency':.8,'current_limit_A':3,'torque_N_m':.2,'speed_rad_s':20}
THERMAL = {'units':'SI','data_basis':'synthetic_validation','initial_K':300,'ambient_K':300,
    'heat_W':8,'thermal_resistance_K_W':10,'thermal_capacity_J_K':5,'duration_s':10,'maximum_K':350}


@pytest.mark.parametrize('torque,speed',[(.2,20),(-.1,40),(.1,-40),(-.2,-20)])
@pytest.mark.parametrize('regen',[False,True])
def test_motor_energy_identity_in_all_quadrants(torque,speed,regen):
    result = motor.analyze({**MOTOR,'torque_N_m':torque,'speed_rad_s':speed,'regeneration_supported':regen})
    assert result['current_A'] == pytest.approx(torque/.1)
    assert result['motor_electrical_W'] == pytest.approx(torque*speed+2*(torque/.1)**2)
    assert result['battery_W'] == pytest.approx(result['mechanical_W']+result['copper_W']+result['driver_heat_W'])
    if not regen:
        assert result['battery_W'] >= 0


def test_motor_back_emf_limits_and_phase_convention():
    zero = motor.analyze({**MOTOR,'torque_N_m':0,'speed_rad_s':100})
    assert zero['required_terminal_voltage_V'] == 10 and zero['current_A'] == 0
    limited = motor.analyze({**MOTOR,'current_limit_A':1,'bus_voltage_V':3})
    assert set(limited['violations']) == {'current_limit','voltage_headroom'}
    for change in ({'motor_convention':'phase_rms'},{'back_emf_V_s_rad':.01},{'regeneration_supported':1}):
        with pytest.raises(ValueError):motor.analyze({**MOTOR,**change})


def test_thermal_step_cooling_and_interval_splitting():
    result = thermal.analyze(THERMAL)
    assert result['end_K'] == pytest.approx(300+80*(1-math.exp(-.2)))
    first = thermal.analyze({**THERMAL,'duration_s':4})
    second = thermal.analyze({**THERMAL,'duration_s':6,'initial_K':first['end_K']})
    assert second['end_K'] == pytest.approx(result['end_K'])
    cooled = thermal.analyze({**THERMAL,'initial_K':400,'heat_W':0,'maximum_K':350})
    assert cooled['end_K'] < 400 and cooled['peak_K'] == 400 and cooled['state'] == 'fail'
    tiny = thermal.analyze({**THERMAL,'duration_s':1e-10})
    assert tiny['end_K'] == pytest.approx(300+8/5*1e-10)
    long = thermal.analyze({**THERMAL,'duration_s':1e6})
    assert long['end_K'] == pytest.approx(380)
