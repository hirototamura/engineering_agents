import itertools
import numpy as np
import pytest
pytest.importorskip('scipy')
pytest.importorskip('mujoco')
from scipy.spatial.transform import Rotation
from environment.isaac.conditions import body_com, corner_frame, initial_pose, trial_plan, sensor_noise
from environment.mujoco.model import equilibrium_rotation
from environment.mujoco.contact import SensorPipeline

CFG={'physics':{'cube_side_m':.18,'wheel_face_inset_m':.012,'wheel_mount_side':'near_corner_000',
    'frame_mass_kg':.55,'frame_com_fraction':[.5]*3,'wheel_mass_kg':.06},
    'sensing':{'tilt_noise_std_deg':.05,'gyro_noise_std_deg_s':.2}}

def test_all_corners_place_support_on_floor_and_com_above_it():
    for bits in itertools.product('01',repeat=3):
        corner=''.join(bits)
        pose,direction,point=initial_pose(CFG,{'corner':corner,'initial_tilt_deg':[0,0]})
        r=Rotation.from_quat(pose[3:]).as_matrix()
        np.testing.assert_allclose(r@point+pose[:3],[0,0,.004],atol=1e-14)
        com=r@body_com(CFG['physics'])+pose[:3]
        np.testing.assert_allclose(com[:2],0,atol=1e-14)
        assert com[2]>.004
        assert np.linalg.det(r)==pytest.approx(1)
    np.testing.assert_allclose(corner_frame(CFG['physics'],'000')[2],equilibrium_rotation('vertex'),atol=1e-14)

def test_seeded_plan_balances_corners_and_is_repeatable():
    a=trial_plan(80); assert a==trial_plan(80)
    assert a!=trial_plan(80,seed=9)
    assert len({c['id'] for c in a['cases']})==80
    assert all(sum(c['corner']==x['corner'] for c in a['cases'])==10 for x in a['cases'])
    with pytest.raises(ValueError): trial_plan(9)

def test_noise_matches_native_sensor_random_stream():
    cases=[{'seed':s} for s in (5,23)]
    noise=sensor_noise(cases,CFG,10)
    for i,c in enumerate(cases):
        pipeline=SensorPipeline({**CFG['sensing'],'seed':c['seed']})
        for k in range(10):
            np.testing.assert_array_equal(pipeline.sample(k*.015,[0,0],[0,0,0]),noise[k,i])
