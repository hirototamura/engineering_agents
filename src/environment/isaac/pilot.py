"""Isaac cube wiring rollout. Not yet a qualified engineering evaluator."""

def main(argv=None):
    import argparse
    import json
    import os
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--num-envs', type=int, default=1)
    parser.add_argument('--duration', type=float, default=1.0)
    parser.add_argument('--video', action='store_true')
    args = parser.parse_args(argv)
    import numpy as np
    from scipy.spatial.transform import Rotation
    import torch
    args.output.mkdir(parents=True, exist_ok=False)
    payload = json.loads((args.input/'input.json').read_text())
    cfg = payload['compiled']['config']; p = cfg['physics']
    usd = json.loads((args.input/'conversion.json').read_text())['usd_path']
    if not os.environ.get('CUDA_VISIBLE_DEVICES', '').startswith('GPU-'):
        raise RuntimeError('Select an allocated GPU by UUID')
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError('Exactly one CUDA GPU is required')

    from isaaclab.app import launch_simulation
    from isaaclab_physx.physics import PhysxCfg
    from isaaclab_physx.sim.schemas import PhysxArticulationCfg, PhysxRigidBodyCfg
    import isaaclab.sim as sim_utils
    from isaaclab.assets import ArticulationCfg, AssetBaseCfg
    from isaaclab.actuators import ImplicitActuatorCfg
    from isaaclab.scene import InteractiveSceneCfg
    from isaaclab.utils import configclass, instantiate
    from isaaclab.sensors import CameraCfg, ContactSensorCfg
    from isaaclab_physx.renderers import IsaacRtxRendererCfg

    @configclass
    class SceneCfg(InteractiveSceneCfg):
        ground = AssetBaseCfg(prim_path='/World/Ground', spawn=sim_utils.GroundPlaneCfg())
        light = AssetBaseCfg(prim_path='/World/Light', spawn=sim_utils.DistantLightCfg(intensity=2500))
        cube = ArticulationCfg(prim_path='{ENV_REGEX_NS}/Cube',
            spawn=sim_utils.UsdFileCfg(usd_path=usd, variants={'Physics':'physx'}, activate_contact_sensors=True,
                rigid_props=PhysxRigidBodyCfg(enable_gyroscopic_forces=True, max_angular_velocity=2000),
                articulation_props=PhysxArticulationCfg(enabled_self_collisions=False,
                    solver_position_iteration_count=16, solver_velocity_iteration_count=4,
                    sleep_threshold=0, stabilization_threshold=0)),
            actuators={'wheels': ImplicitActuatorCfg(joint_names_expr=['rotor_.*'],
                joint_effort_limit=p['motor_torque_limit_nm'], stiffness=0, damping=0)})
        camera = CameraCfg(prim_path='{ENV_REGEX_NS}/Camera', width=640, height=480,
            data_types=['rgb'], spawn=sim_utils.PinholeCameraCfg(focal_length=24),
            renderer_cfg=IsaacRtxRendererCfg()) if args.video else None
        contact = ContactSensorCfg(prim_path='{ENV_REGEX_NS}/Cube/Geometry/cube',
            filter_prim_paths_expr=['/World/Ground/CollisionPlane'], track_contact_points=True,
            max_contact_data_count_per_prim=32)

    def rotate(q, v):
        u=q[:,:3]; w=q[:,3:4]
        return v + 2*torch.cross(u, torch.cross(u,v,dim=-1)+w*v,dim=-1)

    launcher={'device':'cuda:0','headless':True,'visualizer':[], 'multi_gpu':False,
        'enable_cameras':args.video,
        'kit_args':'--/renderer/multiGpu/enabled=false --/renderer/multiGpu/activeCudaGpus=0,'}
    with launch_simulation(PhysxCfg(), launcher):
        sim=sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=p['timestep_s'], device='cuda:0',
            physics=PhysxCfg(), gravity=(0,0,-p['gravity_m_s2'])))
        scene=instantiate(SceneCfg(num_envs=args.num_envs, env_spacing=1.0, replicate_physics=True))
        sim.reset()
        robot=scene['cube']
        names=robot.joint_names
        assert set(names)=={'rotor_0','rotor_1','rotor_2'}, names
        ids=[names.index(f'rotor_{i}') for i in range(3)]
        r0=np.array([[1,-1,0],[1,1,-2],[1,1,1]])/np.array([[2**.5],[6**.5],[3**.5]])
        r=Rotation.from_rotvec(np.deg2rad([1,0,0])).as_matrix()@r0
        pose=torch.zeros((args.num_envs,7),device='cuda:0')
        pose[:,:3]=scene.env_origins; pose[:,2]+=cfg.get('contact',{}).get('corner_radius_m',.004)
        pose[:,3:]=torch.tensor(Rotation.from_matrix(r).as_quat(),device='cuda:0')
        robot.write_root_pose_to_sim_index(root_pose=pose)
        robot.write_root_velocity_to_sim_index(root_velocity=torch.zeros((args.num_envs,6),device='cuda:0'))
        robot.write_joint_position_to_sim_index(position=torch.zeros_like(robot.data.default_joint_pos.torch))
        robot.write_joint_velocity_to_sim_index(velocity=torch.zeros_like(robot.data.default_joint_vel.torch))
        scene.reset()
        writer=None
        if args.video:
            import imageio.v2 as imageio
            writer=imageio.get_writer(str(args.output/'cube.mp4'), fps=30, codec='libx264', quality=8)
            camera=scene['camera']
            eyes=scene.env_origins+torch.tensor([.55,-.65,.42],device='cuda:0')
            targets=scene.env_origins+torch.tensor([0,0,.14],device='cuda:0')
            camera.set_world_poses_from_view(eyes,targets)
        K=torch.tensor(payload['compiled']['controller']['K'],device='cuda:0',dtype=torch.float32)
        yaw=payload['compiled']['controller']['yaw_rate_gain_nm_s']
        rows=[]; request=torch.zeros((args.num_envs,3),device='cuda:0')
        substeps=round(p['control_period_s']/p['timestep_s'])
        diag=torch.ones((args.num_envs,3),device='cuda:0')/3**.5
        for step in range(round(args.duration/p['timestep_s'])+1):
            state=robot.data.root_link_pose_w.torch
            q=state[:,3:]; rates=robot.data.joint_vel.torch[:,ids]
            omega=robot.data.root_link_vel_w.torch[:,3:]
            direction=rotate(q,diag)
            tilt=torch.stack((torch.atan2(-direction[:,1],direction[:,2]),torch.atan2(direction[:,0],direction[:,2])),dim=-1)
            momentum=rotate(q,rates*p['wheel_axial_inertia_kg_m2'])
            if step%substeps==0:
                contact_force=scene['contact'].data.net_normal_forces_w.torch
                x=torch.cat((tilt,omega[:,:2],momentum[:,:2]),dim=-1)
                world=torch.cat((-x@K.T,yaw*omega[:,2:3]),dim=-1)
                qi=torch.cat((-q[:,:3],q[:,3:]),dim=-1)
                request=rotate(qi,world)
                rows.append({'time_s':step*p['timestep_s'],'pose_xyzw':state[0].tolist(),
                    'tilt_deg':tilt[0].mul(180/np.pi).tolist(),'wheel_rad_s':rates[0].tolist(),
                    'requested_torque_nm':request[0].tolist(), 'normal_force_n':float(contact_force[0,:,2].sum())})
            if not torch.isfinite(state).all(): raise RuntimeError('Nonfinite PhysX state')
            if args.video and step%round(1/(30*p['timestep_s']))==0:
                sim.render()
                camera.update(1/30,force_recompute=True)
                writer.append_data(camera.data.output['rgb'][0].cpu().numpy())
            if step==round(args.duration/p['timestep_s']): break
            peak=min(p['motor_torque_limit_nm'],cfg.get('actuation',{}).get('peak_torque_nm',p['motor_torque_limit_nm']))
            budget=peak*(1-rates.abs()/cfg.get('actuation',{}).get('no_load_speed_rad_s',p['wheel_speed_limit_rad_s'])).clamp(min=0)
            applied=request.clamp(-budget,budget)
            applied[(rates.abs()>=p['wheel_speed_limit_rad_s'])&(applied.sign()==rates.sign())]=0
            robot.actuators.target_command.set_effort_index(value=applied,joint_ids=ids)
            scene.write_data_to_sim(); sim.step(render=False); scene.update(p['timestep_s'])
        (args.output/'telemetry.json').write_text(json.dumps(rows,indent=2)+'\n')
        if writer is not None: writer.close()
        (args.output/'run.json').write_text(json.dumps({'status':'wiring_only','backend':'isaacsim_physx',
            'gpu_uuid':os.environ['CUDA_VISIBLE_DEVICES'],'num_envs':args.num_envs,
            'sensing':'ideal; delay/noise not yet implemented','physical_verified':False,
            'source_snapshot':payload['snapshot']['source_snapshot_ref']},indent=2)+'\n')
        print('Saved',args.output,flush=True)
        sensor=scene['contact']
        print('CONTACT VIEW', type(sensor.contact_view), flush=True)
        data=sensor.contact_view.get_normal_contact_data(dt=p['timestep_s'])
        print('CONTACT SHAPES', [(type(x).__name__,getattr(x,'shape',None)) for x in data],flush=True)


if __name__ == "__main__":
    main()
