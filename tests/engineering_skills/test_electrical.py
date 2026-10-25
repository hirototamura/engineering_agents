import math
import pytest
from environment.engineering_analysis.electrical import analyze

BASE={'units':'SI','data_basis':'synthetic_validation','motor_convention':'effective_dc','torque_constant_N_m_A':.1,'back_emf_V_s_rad':.1,
      'winding_resistance_ohm':2.,'bus_voltage_V':12.,'driver_efficiency':.8,'current_limit_A':3.,'maximum_winding_K':400.,
      'thermal_resistance_K_W':10.,'thermal_capacity_J_K':5.,'motor_count':1,
      'modes':[{'name':'drive','duration_s':10.,'torque_N_m':.2,'speed_rad_s':20.}]}


def test_power_energy_and_thermal_closed_form():
    r=analyze(BASE);m=r['modes'][0]
    assert m['current_A_per_motor']==pytest.approx(2.)
    assert m['required_terminal_voltage_V']==pytest.approx(6.)
    assert m['motor_electrical_W_per_motor']==pytest.approx(m['mechanical_W_per_motor']+m['copper_W_per_motor'])
    assert r['net_battery_energy_J']==pytest.approx(150.)
    assert m['end_winding_K']==pytest.approx(298.15+80*(1-math.exp(-10/50)))


def test_regeneration_is_opt_in_and_energy_is_conserved():
    mode={'name':'brake','duration_s':5.,'torque_N_m':-.1,'speed_rad_s':40.}
    d={**BASE,'modes':[mode]}
    off=analyze(d)['modes'][0];on=analyze({**d,'regeneration_supported':True})['modes'][0]
    assert off['battery_W_all_motors']==0 and off['braking_dump_W_per_motor']==pytest.approx(2.)
    assert on['battery_W_all_motors']==pytest.approx(-1.6)
    assert on['driver_heat_W_per_motor']==pytest.approx(.4)


def test_temperature_carries_between_modes_and_limits_are_visible():
    one=BASE['modes'][0]
    split=analyze({**BASE,'modes':[{**one,'duration_s':5.},{**one,'duration_s':5.}]})
    assert split['modes'][-1]['end_winding_K']==pytest.approx(analyze(BASE)['modes'][0]['end_winding_K'])
    invalid=analyze({**BASE,'current_limit_A':1.,'bus_voltage_V':3.})
    assert not invalid['feasible']
    assert set(invalid['modes'][0]['violations'])=={'current_limit','voltage_headroom'}


def test_phase_convention_and_constants_cannot_be_silently_mixed():
    with pytest.raises(ValueError):analyze({**BASE,'motor_convention':'phase_rms'})
    with pytest.raises(ValueError):analyze({**BASE,'back_emf_V_s_rad':.01})
