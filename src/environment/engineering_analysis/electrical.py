"""Composition: per-mode motor points and sequential thermal intervals."""
from .common import number, require_units
from . import motor, thermal


def jobs(data, results):
    require_units(data)
    count = data.get('motor_count', 1)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100:
        raise ValueError('motor_count shall be an integer in 1..100')
    if not 1 <= len(data['modes']) <= 100:
        raise ValueError('Supply 1..100 sequential operating modes')
    ambient = number(data.get('ambient_K', 298.15), 'ambient_K', positive=True)
    temperature = number(data.get('initial_winding_K', ambient), 'initial winding temperature', positive=True)
    for i, mode in enumerate(data['modes']):
        number(mode['duration_s'], 'mode duration', positive=True)
        point, heat = f'mode{i:03d}-point', f'mode{i:03d}-temperature'
        yield point, 'motor-operating-point', {**data, **mode}
        yield heat, 'first-order-thermal-response', {
            'units':data['units'], 'data_basis':data['data_basis'], 'initial_K':temperature,
            'ambient_K':ambient, 'heat_W':results[point]['copper_W'], 'duration_s':mode['duration_s'],
            'thermal_resistance_K_W':data['thermal_resistance_K_W'],
            'thermal_capacity_J_K':data['thermal_capacity_J_K'], 'maximum_K':data['maximum_winding_K']}
        temperature = results[heat]['end_K']


def analyze(data, dependencies=None):
    if dependencies is None:
        dependencies = {}
        for role, skill, value in jobs(data, dependencies):
            dependencies[role] = motor.analyze(value) if skill == 'motor-operating-point' else thermal.analyze(value)
    rows = []
    net = drawn = returned = duration = 0.
    count = data.get('motor_count', 1)
    for i, mode in enumerate(data['modes']):
        point, heat = dependencies[f'mode{i:03d}-point'], dependencies[f'mode{i:03d}-temperature']
        violations = list(point['violations'])
        if heat['state'] == 'fail':
            violations.append('winding_temperature')
        seconds = mode['duration_s']
        rows.append({'mode':mode['name'], 'duration_s':seconds,
            'current_A_per_motor':point['current_A'], 'required_terminal_voltage_V':point['required_terminal_voltage_V'],
            'mechanical_W_per_motor':point['mechanical_W'], 'copper_W_per_motor':point['copper_W'],
            'motor_electrical_W_per_motor':point['motor_electrical_W'], 'driver_heat_W_per_motor':point['driver_heat_W'],
            'braking_dump_W_per_motor':point['braking_dump_W'], 'battery_W_all_motors':count*point['battery_W'],
            'battery_current_A':count*point['battery_current_A'], 'end_winding_K':heat['end_K'],
            'peak_winding_K':heat['peak_K'], 'violations':violations, 'requested_operating_point_feasible':not violations})
        energy = count*point['battery_W']*seconds
        net += energy; drawn += max(energy,0); returned += max(-energy,0); duration += seconds
    return {'motor_convention':'effective_dc; phase/line definitions shall be converted before use',
        'modes':rows, 'net_battery_energy_J':net, 'drawn_energy_J':drawn, 'returned_energy_J':returned,
        'average_battery_W':net/duration, 'feasible':all(r['requested_operating_point_feasible'] for r in rows),
        'limitations':['Infeasible requested points are flagged, not treated as achieved motor output.',
            'Constant bus voltage and winding resistance; switching ripple, iron/friction losses and cell voltage sag excluded.',
            'Winding thermal model excludes driver-to-winding conduction and enclosure heat paths.',
            'Regeneration requires verified driver and battery charge capability. No actuator commands are sent.']}
