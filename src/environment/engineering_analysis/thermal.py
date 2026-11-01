"""Exact constant-load response of a lumped first-order thermal network."""
import math
from .common import number, require_units


def analyze(data):
    require_units(data)
    initial = number(data['initial_K'], 'initial temperature', positive=True)
    ambient = number(data['ambient_K'], 'ambient temperature', positive=True)
    resistance = number(data['thermal_resistance_K_W'], 'thermal resistance', positive=True)
    capacity = number(data['thermal_capacity_J_K'], 'thermal capacity', positive=True)
    duration = number(data['duration_s'], 'duration', positive=True)
    heat = number(data['heat_W'], 'heat generation', nonnegative=True)
    fraction = -math.expm1(-duration/(resistance*capacity))
    end = initial+(ambient+heat*resistance-initial)*fraction
    maximum = max(initial, end)
    limit = data.get('maximum_K')
    if limit is not None:
        limit = number(limit, 'maximum temperature', positive=True)
    return {'end_K': end, 'peak_K': maximum, 'time_constant_s': resistance*capacity,
            'equilibrium_K': ambient+heat*resistance,
            'state': 'unassessed' if limit is None else 'pass' if maximum <= limit else 'fail',
            'limitations': ['One lumped node with constant heat, ambient, resistance and capacity during this interval.']}
