"""Composition: nominal rigid properties plus bounded Monte Carlo propagation."""
import copy
import numpy as np
from .common import require_units
from .mass_properties import properties, validate_parts


def jobs(data, results):
    yield 'nominal', 'rigid-body-mass-properties', data


def analyze(data, dependencies=None):
    require_units(data)
    validate_parts(data)
    result = dict(dependencies["nominal"]) if dependencies is not None else properties(data["parts"])
    samples = data.get('uncertainty_samples', 1000)
    if isinstance(samples, bool) or not isinstance(samples, int) or not 100 <= samples <= 10000:
        raise ValueError('uncertainty_samples shall be an integer in 100..10000')
    if samples*len(data['parts']) > 250000:
        raise ValueError('Uncertainty work budget exceeds 250000 part samples')
    rng = np.random.default_rng(data.get('seed', 0))
    draws = []
    # Uniform independent bounded intervals, not Gaussian errors or confidence claims.
    for _ in range(samples):
        parts = copy.deepcopy(data['parts'])
        for part in parts:
            if part.get('mass_kg') is None:
                continue
            for key in ('mass_kg', 'center_m'):
                bounds = part.get('uncertainty_bounds', {}).get(key)
                if bounds is not None:
                    low, high = np.asarray(bounds, dtype=float)
                    expected = () if key == 'mass_kg' else (3,)
                    if low.shape != expected or high.shape != expected or not np.all(np.isfinite([low, high])) or np.any(low > high):
                        raise ValueError('Uncertainty bounds have invalid shape or order')
                    if key == 'mass_kg' and low < 0:
                        raise ValueError('Mass uncertainty cannot be negative')
                    draw = rng.uniform(low, high)
                    part[key] = float(draw) if key == 'mass_kg' else draw.tolist()
        value = properties(parts)['known_parts']
        draws.append([value['mass_kg'], *value['com_m'], *np.diag(value['inertia_at_com_kg_m2'])])
    array = np.array(draws)
    result['uncertainty'] = {'method': 'independent bounded uniform inputs; empirical central 95% range, not confidence or worst-case guarantee',
                             'samples': samples, 'seed': data.get('seed', 0), 'columns': ['mass_kg', 'com_x_m', 'com_y_m', 'com_z_m', 'Ixx', 'Iyy', 'Izz'],
                             'q025': np.quantile(array, .025, axis=0).tolist(), 'q975': np.quantile(array, .975, axis=0).tolist()}
    result['limitations'] = ['Mass uncertainty scales primitive and nominal CAD inertia at fixed geometry.',
                             'Uniform primitives and CAD tensors do not infer printed infill or missing purchased masses.',
                             'Uncertainty inputs are independent unless a different joint model is supplied externally.']
    return result
