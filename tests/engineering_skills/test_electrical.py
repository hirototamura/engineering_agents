import pytest
from environment.engineering_analysis.electrical import analyze, jobs

BASE={'units':'SI','data_basis':'synthetic_validation','motor_convention':'effective_dc','torque_constant_N_m_A':.1,'back_emf_V_s_rad':.1,
      'winding_resistance_ohm':2.,'bus_voltage_V':12.,'driver_efficiency':.8,'current_limit_A':3.,'maximum_winding_K':400.,
      'thermal_resistance_K_W':10.,'thermal_capacity_J_K':5.,'motor_count':1,
      'modes':[{'name':'drive','duration_s':10.,'torque_N_m':.2,'speed_rad_s':20.}]}


def test_mode_energy_aggregation_and_temperature_use_qualified_child_results():
    point={'current_A':2,'required_terminal_voltage_V':6,'mechanical_W':4,'copper_W':8,
           'motor_electrical_W':12,'driver_heat_W':3,'braking_dump_W':0,'battery_W':15,
           'battery_current_A':1.25,'violations':[]}
    deps={'mode000-point':point,'mode000-temperature':{'end_K':311,'peak_K':311,'state':'pass'}}
    r=analyze(BASE,deps);m=r['modes'][0]
    assert m['current_A_per_motor']==2 and m['end_winding_K']==311
    assert r['net_battery_energy_J']==pytest.approx(150.)


def test_motor_regeneration_policy_and_operating_point_are_forwarded():
    mode={'name':'brake','duration_s':5.,'torque_N_m':-.1,'speed_rad_s':40.}
    d={**BASE,'modes':[mode]}
    for regen in (False,True):
        _,skill,value=next(jobs({**d,'regeneration_supported':regen},{}))
        assert skill=='motor-operating-point'
        assert value['regeneration_supported']==regen
        assert value['torque_N_m']==-.1 and value['speed_rad_s']==40


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
