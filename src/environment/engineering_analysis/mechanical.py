"""Rigid mass properties with frame transforms and bounded Monte Carlo inputs."""
import copy
import numpy as np
from .common import number, vector, require_units


def properties(parts):
    rows = []
    for part in parts:
        mass = part.get('mass_kg')
        center = vector(part['center_m'], 'center_m')
        if mass is None:
            rows.append({'id': part['id'], 'mass_kg': None, 'center_m': center.tolist()})
            continue
        mass = number(mass, 'mass_kg', nonnegative=True)
        shape = part['shape']
        if shape['type'] == 'box':
            x, y, z = vector(shape['size_m'], 'size_m')
            if min(x, y, z) <= 0:
                raise ValueError('Box dimensions shall be positive')
            local = np.diag([y*y+z*z, x*x+z*z, x*x+y*y])*mass/12
        elif shape['type'] == 'annular_cylinder':
            outer = number(shape['outer_radius_m'], 'outer radius', positive=True)
            inner = number(shape.get('inner_radius_m', 0), 'inner radius', nonnegative=True)
            height = number(shape['height_m'], 'height', positive=True)
            if inner >= outer:
                raise ValueError('Inner radius shall be smaller than outer radius')
            transverse = mass*(3*(outer*outer+inner*inner)+height*height)/12
            local = np.diag([transverse, transverse, mass*(outer*outer+inner*inner)/2])
        elif shape['type'] == 'cad_tensor':
            reference_mass = number(shape['reference_mass_kg'], 'reference mass', positive=True)
            local = np.asarray(shape['inertia_at_com_kg_m2'], dtype=float)*mass/reference_mass
            if local.shape != (3, 3) or not np.all(np.isfinite(local)):
                raise ValueError('CAD inertia shall be a finite 3x3 tensor')
        else:
            raise ValueError('Unsupported mass shape')
        if not np.allclose(local, local.T, atol=1e-12) or np.min(np.linalg.eigvalsh(local)) < -1e-12:
            raise ValueError('Inertia shall be symmetric positive semidefinite')
        principal = np.linalg.eigvalsh(local)
        if principal[-1] > sum(principal[:2])+1e-10:
            raise ValueError('Inertia principal moments violate the triangle inequality')
        rotation = np.asarray(part.get('rotation_local_to_body', np.eye(3)), dtype=float)
        if rotation.shape != (3, 3) or not np.allclose(rotation.T@rotation, np.eye(3), atol=1e-8) or not np.isclose(np.linalg.det(rotation), 1):
            raise ValueError('Part rotation shall be a proper orthonormal matrix')
        inertia = rotation@local@rotation.T
        rows.append({'id': part['id'], 'mass_kg': mass, 'center_m': center.tolist(), 'inertia_at_part_com_kg_m2': inertia.tolist()})
    known = [r for r in rows if r['mass_kg'] is not None]
    total = sum(r['mass_kg'] for r in known)
    if total <= 0:
        raise ValueError('At least one positive known mass is required')
    center = sum((r['mass_kg']*np.array(r['center_m']) for r in known), np.zeros(3))/total
    inertia = np.zeros((3, 3))
    for row in known:
        delta = np.array(row['center_m'])-center
        inertia += np.array(row['inertia_at_part_com_kg_m2'])+row['mass_kg']*((delta@delta)*np.eye(3)-np.outer(delta, delta))
    return {'parts': rows, 'complete': len(known) == len(rows), 'missing_mass_ids': [r['id'] for r in rows if r['mass_kg'] is None],
            'known_parts': {'mass_kg': total, 'com_m': center.tolist(), 'inertia_at_com_kg_m2': inertia.tolist(),
                            'principal_moments_kg_m2': np.linalg.eigvalsh(inertia).tolist()},
            'system': {'mass_kg': total, 'com_m': center.tolist(), 'inertia_at_com_kg_m2': inertia.tolist()} if len(known) == len(rows) else None,
            'tensor_convention': 'Ixy=-integral(x*y dm); engineering products of inertia use the opposite sign'}


def analyze(data):
    require_units(data)
    if not data['parts'] or len(data['parts']) > 1000 or len({p['id'] for p in data['parts']}) != len(data['parts']):
        raise ValueError('Parts shall have unique IDs, with 1..1000 entries')
    result = properties(data['parts'])
    samples = data.get('uncertainty_samples', 1000)
    if isinstance(samples, bool) or not isinstance(samples, int) or not 100 <= samples <= 10000:
        raise ValueError('uncertainty_samples shall be an integer in 100..10000')
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
