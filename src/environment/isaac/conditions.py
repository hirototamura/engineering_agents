"""Seeded eight-corner initial states, in SI units and explicit XYZW order."""
import itertools
import numpy as np


def body_com(physics):
    side = physics['cube_side_m']
    centers = np.full((3, 3), side/2)
    near = physics.get('wheel_mount_side', 'far_corner_000') == 'near_corner_000'
    np.fill_diagonal(centers, physics['wheel_face_inset_m'] if near else side-physics['wheel_face_inset_m'])
    frame = np.array(physics['frame_com_fraction'])*side
    return (frame*physics['frame_mass_kg']+centers.sum(0)*physics['wheel_mass_kg'])/(physics['frame_mass_kg']+3*physics['wheel_mass_kg'])


def corner_frame(physics, corner):
    bits=np.array([int(c) for c in corner])
    if len(bits)!=3 or not np.isin(bits,[0,1]).all():
        raise ValueError('Corner must be a three-bit identifier')
    point=bits*physics['cube_side_m']
    direction=body_com(physics)-point
    direction/=np.linalg.norm(direction)
    x=np.cross(direction,[0.,0.,1.]); x/=np.linalg.norm(x)
    rotation=np.stack((x,np.cross(direction,x),direction))
    return point,direction,rotation


def initial_pose(config, case):
    from scipy.spatial.transform import Rotation

    corner,direction,r0=corner_frame(config['physics'],case['corner'])
    tilt=np.deg2rad(case['initial_tilt_deg'])
    rotation=Rotation.from_rotvec([*tilt,0]).as_matrix()@r0
    radius=config.get('contact',{}).get('corner_radius_m',.004)
    position=np.array([0.,0.,radius])-rotation@corner
    return np.r_[position,Rotation.from_matrix(rotation).as_quat()],direction,corner


def trial_plan(count=24576, seed=20261023, duration=6.0):
    if count<=0 or count%8:
        raise ValueError('Trial count must be positive and divisible by eight')
    if duration<=0 or not np.isfinite(duration):
        raise ValueError('Duration must be finite and positive')
    rng=np.random.default_rng(seed)
    corners=[''.join(map(str,b)) for b in itertools.product((0,1),repeat=3)]
    cases=[]
    for i in range(count):
        angle=rng.uniform(0,5); azimuth=rng.uniform(-np.pi,np.pi)
        cases.append({'id':f'corner-{corners[i%8]}-{i:06d}','corner':corners[i%8],
            'initial_tilt_deg':(angle*np.array([np.cos(azimuth),np.sin(azimuth)])).tolist(),
            'initial_yaw_rate_rad_s':float(rng.uniform(-1,1)),
            'seed':int(rng.integers(0,2**31-1)), 'duration_s':duration})
    return {'schema_version':1,'seed':seed,'trial_count':count,'cases':cases,
            'scope':'exploration; not a human-adopted baseline or physical acceptance',
            'distribution':{'corner':'balanced 8-way','tilt_radius_deg':'uniform [0,5]',
                            'tilt_azimuth_rad':'uniform [-pi,pi]','yaw_rate_rad_s':'uniform [-1,1]'}}


def sensor_noise(cases, config, samples):
    sensing=config.get('sensing',{})
    scale=np.deg2rad([sensing.get('tilt_noise_std_deg',0)]*2+[sensing.get('gyro_noise_std_deg_s',0)]*3)
    return np.stack([np.random.default_rng(c['seed']).standard_normal((samples,5))*scale for c in cases],axis=1)
