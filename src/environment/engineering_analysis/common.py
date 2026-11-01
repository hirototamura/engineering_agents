"""Input guards shared by engineering calculations."""
import math
import numpy as np


def number(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} shall be a finite SI number')
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError(f'{name} has an invalid sign')
    return float(value)


def vector(value, name, length=3):
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f'{name} shall contain {length} values')
    return np.array([number(v, name) for v in value])


def require_units(data):
    if data.get('units') != 'SI':
        raise ValueError('Input units shall be SI; convert explicitly before analysis')
    if data.get('data_basis') not in ('assumed', 'measured', 'derived', 'synthetic_validation'):
        raise ValueError('data_basis shall distinguish assumed, measured, derived or synthetic_validation data')
