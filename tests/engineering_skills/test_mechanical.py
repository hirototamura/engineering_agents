import copy
import numpy as np
import pytest
from environment.engineering_analysis.mechanical import analyze, properties


def box(id='a', mass=2., center=None, size=None):
    return {'id':id, 'mass_kg':mass, 'center_m':center or [0,0,0], 'shape':{'type':'box','size_m':size or [1,1,1]}}


def test_cube_and_rotated_annular_cylinder_closed_form():
    r = properties([box()])
    assert np.diag(r['system']['inertia_at_com_kg_m2']) == pytest.approx([1/3]*3)
    p = {'id':'wheel', 'mass_kg':2.,'center_m':[0,0,0], 'shape':{'type':'annular_cylinder','outer_radius_m':2.,'inner_radius_m':1.,'height_m':.6},
         'rotation_local_to_body':[[0,0,1],[0,1,0],[-1,0,0]]}
    i = np.array(properties([p])['system']['inertia_at_com_kg_m2'])
    assert np.diag(i) == pytest.approx([5.,2*(15+.36)/12,2*(15+.36)/12])


def test_parallel_axis_cross_terms_and_translation_invariance():
    parts = [box('a',1,[-1,-1,0],[1e-6]*3),box('b',1,[1,1,0],[1e-6]*3)]
    r = properties(parts)['system']
    assert r['com_m'] == pytest.approx([0,0,0])
    assert np.array(r['inertia_at_com_kg_m2']) == pytest.approx(np.array([[2,-2,0],[-2,2,0],[0,0,4]]), abs=1e-10)
    moved = copy.deepcopy(parts)
    for p in moved:p['center_m'] = (np.array(p['center_m'])+[5,7,9]).tolist()
    assert properties(moved)['system']['inertia_at_com_kg_m2'] == pytest.approx(np.array(r['inertia_at_com_kg_m2']))


def test_missing_mass_and_seeded_uncertainty_are_explicit():
    p = box();p['uncertainty_bounds']={'mass_kg':[1.8,2.2], 'center_m':[[-.01,-.02,-.03],[.01,.02,.03]]}
    missing = box('battery',None)
    d={'units':'SI','data_basis':'synthetic_validation','parts':[p,missing],'seed':7,'uncertainty_samples':100}
    r = analyze(d)
    assert r['system'] is None and r['missing_mass_ids']==['battery']
    assert analyze(d)['uncertainty'] == r['uncertainty']
    assert 1.8 <= r['uncertainty']['q025'][0] < r['uncertainty']['q975'][0] <= 2.2


def test_invalid_rotation_and_unphysical_tensor_rejected():
    bad = box();bad['rotation_local_to_body']=[[-1,0,0],[0,1,0],[0,0,1]]
    with pytest.raises(ValueError):properties([bad])
    bad=box();bad['shape']={'type':'cad_tensor','reference_mass_kg':2,'inertia_at_com_kg_m2':[[10,0,0],[0,1,0],[0,0,1]]}
    with pytest.raises(ValueError):properties([bad])
