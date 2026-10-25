"""One effective-DC motor/driver operating point, independent of a project."""
import math
from .common import number, require_units


def analyze(data):
    require_units(data)
    if data.get('motor_convention') != 'effective_dc':
        raise ValueError('Convert phase/line constants to a documented effective_dc convention first')
    kt = number(data['torque_constant_N_m_A'], 'torque constant', positive=True)
    ke = number(data['back_emf_V_s_rad'], 'back EMF', positive=True)
    if not math.isclose(kt, ke, rel_tol=.001):
        raise ValueError('Effective-DC SI torque/back-EMF constants shall agree')
    resistance = number(data['winding_resistance_ohm'], 'resistance', positive=True)
    bus = number(data['bus_voltage_V'], 'bus voltage', positive=True)
    efficiency = number(data['driver_efficiency'], 'driver efficiency', positive=True)
    duty = number(data.get('max_duty_fraction', .95), 'maximum duty', positive=True)
    if efficiency > 1 or duty > 1:
        raise ValueError('Efficiency and maximum duty cannot exceed one')
    current_limit = number(data['current_limit_A'], 'current limit', positive=True)
    regen = data.get('regeneration_supported', False)
    if not isinstance(regen, bool):
        raise ValueError('regeneration_supported shall be Boolean')
    idle = number(data.get('driver_idle_W_per_motor', 0), 'driver idle', nonnegative=True)
    torque = number(data['torque_N_m'], 'torque')
    omega = number(data['speed_rad_s'], 'speed')
    current = torque/kt
    voltage = ke*omega+resistance*current
    copper, mechanical, terminal = resistance*current*current, torque*omega, voltage*current
    dump = 0.
    if terminal >= 0:
        battery = terminal/efficiency+idle
        driver_heat = terminal*(1/efficiency-1)+idle
    elif regen:
        battery = terminal*efficiency+idle
        driver_heat = -terminal*(1-efficiency)+idle
    else:
        battery, dump = idle, -terminal
        driver_heat = dump+idle
    violations = []
    if abs(current) > current_limit:
        violations.append('current_limit')
    if abs(voltage) > bus*duty:
        violations.append('voltage_headroom')
    return {'current_A': current, 'required_terminal_voltage_V': voltage, 'mechanical_W': mechanical,
            'copper_W': copper, 'motor_electrical_W': terminal, 'driver_heat_W': driver_heat,
            'braking_dump_W': dump, 'battery_W': battery, 'battery_current_A': battery/bus,
            'violations': violations, 'feasible': not violations,
            'limitations': ['A requested steady operating point; infeasible output is not achieved motor performance.',
                            'Effective-DC constants, constant bus/resistance; no switching ripple, iron losses or battery sag.']}
