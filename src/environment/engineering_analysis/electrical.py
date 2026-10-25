"""Effective-DC wheel-drive limits, energy accounting and lumped winding heat."""
import math
from .common import number, require_units


def analyze(data):
    require_units(data)
    if data.get('motor_convention') != 'effective_dc':
        raise ValueError('Convert BLDC phase/line constants to a documented effective_dc convention first')
    kt = number(data['torque_constant_N_m_A'], 'torque constant', positive=True)
    ke = number(data['back_emf_V_s_rad'], 'back EMF', positive=True)
    if not math.isclose(kt, ke, rel_tol=.001):
        raise ValueError('Effective-DC SI torque/back-EMF constants shall agree; check phase/line conventions')
    resistance = number(data['winding_resistance_ohm'], 'resistance', positive=True)
    bus = number(data['bus_voltage_V'], 'bus voltage', positive=True)
    efficiency = number(data['driver_efficiency'], 'driver efficiency', positive=True)
    if efficiency > 1:
        raise ValueError('Efficiency cannot exceed one')
    current_limit = number(data['current_limit_A'], 'current limit', positive=True)
    duty = number(data.get('max_duty_fraction', .95), 'maximum duty', positive=True)
    if duty > 1:
        raise ValueError('Duty fraction cannot exceed one')
    ambient = number(data.get('ambient_K', 298.15), 'ambient_K', positive=True)
    max_temp = number(data['maximum_winding_K'], 'maximum winding temperature', positive=True)
    rth = number(data['thermal_resistance_K_W'], 'thermal resistance', positive=True)
    capacity = number(data['thermal_capacity_J_K'], 'thermal capacity', positive=True)
    count = data.get('motor_count', 3)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100:
        raise ValueError('motor_count shall be an integer in 1..100')
    regen = data.get('regeneration_supported', False)
    if not isinstance(regen, bool):
        raise ValueError('regeneration_supported shall be Boolean')
    idle = number(data.get('driver_idle_W_per_motor', 0), 'driver idle', nonnegative=True)
    temperature = ambient
    rows = []
    net = drawn = returned = duration = 0.
    for mode in data['modes']:
        seconds = number(mode['duration_s'], 'mode duration', positive=True)
        torque = number(mode['torque_N_m'], 'motor torque')
        omega = number(mode['speed_rad_s'], 'motor speed')
        current = torque/kt
        voltage = ke*omega+resistance*current
        copper = resistance*current*current
        mechanical = torque*omega
        terminal = voltage*current
        dump = 0.
        if terminal >= 0:
            battery = terminal/efficiency+idle
            driver_heat = terminal*(1/efficiency-1)+idle
        elif regen:
            battery = terminal*efficiency+idle
            driver_heat = -terminal*(1-efficiency)+idle
        else:
            battery = idle
            dump = -terminal
            driver_heat = dump+idle
        temperature = ambient+(temperature-ambient)*math.exp(-seconds/(rth*capacity))+copper*rth*(1-math.exp(-seconds/(rth*capacity)))
        violations = []
        if abs(current) > current_limit:
            violations.append('current_limit')
        if abs(voltage) > bus*duty:
            violations.append('voltage_headroom')
        if temperature > max_temp:
            violations.append('winding_temperature')
        rows.append({'mode': mode['name'], 'duration_s': seconds, 'current_A_per_motor': current,
                     'required_terminal_voltage_V': voltage, 'mechanical_W_per_motor': mechanical,
                     'copper_W_per_motor': copper, 'motor_electrical_W_per_motor': terminal,
                     'driver_heat_W_per_motor': driver_heat, 'braking_dump_W_per_motor': dump,
                     'battery_W_all_motors': count*battery, 'battery_current_A': count*battery/bus,
                     'end_winding_K': temperature, 'violations': violations,
                     'requested_operating_point_feasible': not violations})
        energy = count*battery*seconds
        net += energy
        drawn += max(energy, 0)
        returned += max(-energy, 0)
        duration += seconds
    if not rows:
        raise ValueError('At least one operating mode is required')
    return {'motor_convention': 'effective_dc; phase/line definitions shall be converted before use',
            'modes': rows, 'net_battery_energy_J': net, 'drawn_energy_J': drawn,
            'returned_energy_J': returned, 'average_battery_W': net/duration,
            'feasible': all(r['requested_operating_point_feasible'] for r in rows),
            'limitations': ['Infeasible requested points are flagged, not treated as achieved motor output.',
                            'Constant bus voltage and winding resistance; switching ripple, iron/friction losses and cell voltage sag excluded.',
                            'Winding thermal model excludes driver-to-winding conduction and enclosure heat paths.',
                            'Regeneration requires verified driver and battery charge capability. No actuator commands are sent.']}
