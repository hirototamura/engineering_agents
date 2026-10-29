"""Execute a frozen trial shard with GPU PhysX; emit every failure and raw telemetry."""

def main(argv=None):
    import argparse
    import hashlib
    import json
    import os
    from pathlib import Path
    import sys
    import time

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--cases',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--video',action='store_true',help='Record an eight-corner RTX mosaic (requires exactly eight cases)')
    args=parser.parse_args(argv)
    import numpy as np
    import torch
    import warp as wp
    from environment.isaac.conditions import initial_pose, sensor_noise
    args.output.mkdir(parents=True,exist_ok=False)
    payload=json.loads((args.input/'input.json').read_text())
    cases=json.loads(args.cases.read_text())['cases']; n=len(cases)
    if not n:raise ValueError('Empty trial shard')
    if args.video and n!=8:raise ValueError('The video mosaic requires exactly eight cases')
    cfg=payload['compiled']['config']; p=cfg['physics']; evaluation=cfg['evaluation']
    dt=p['timestep_s']; control_dt=p['control_period_s']; substeps=round(control_dt/dt)
    duration=cases[0]['duration_s']; ticks=round(duration/control_dt)
    if not n or any(c['duration_s']!=duration for c in cases) or not np.isclose(ticks*control_dt,duration):
        raise ValueError('A shard needs a common duration divisible by the control period')
    if not np.isclose(substeps*dt,control_dt): raise ValueError('Nonintegral control interval')
    gpu=os.environ.get('CUDA_VISIBLE_DEVICES','')
    if not gpu.startswith('GPU-') or not torch.cuda.is_available() or torch.cuda.device_count()!=1:
        raise RuntimeError('Exactly one allocated CUDA GPU required')
    if str(torch.cuda.get_device_properties(0).uuid).removeprefix('GPU-')!=gpu.removeprefix('GPU-'):
        raise RuntimeError('GPU identity mismatch')
    usd=json.loads((args.input/'conversion.json').read_text())['usd_path']

    from isaaclab.app import launch_simulation
    from isaaclab_physx.physics import PhysxCfg
    from isaaclab_physx.sim.schemas import PhysxArticulationCfg, PhysxRigidBodyCfg
    import isaaclab.sim as sim_utils
    from isaaclab.assets import ArticulationCfg, AssetBaseCfg
    from isaaclab.actuators import ImplicitActuatorCfg
    from isaaclab.scene import InteractiveSceneCfg
    from isaaclab.sensors import CameraCfg, ContactSensorCfg
    from isaaclab_physx.renderers import IsaacRtxRendererCfg
    from isaaclab.utils import configclass, instantiate

    friction=cfg.get('contact',{}).get('sliding_friction',.7)
    @configclass
    class SceneCfg(InteractiveSceneCfg):
        light=AssetBaseCfg(prim_path='/World/Light',spawn=sim_utils.DistantLightCfg(intensity=2500)) if args.video else None
        camera=CameraCfg(prim_path='{ENV_REGEX_NS}/Camera',width=320,height=240,
            data_types=['rgb'],spawn=sim_utils.PinholeCameraCfg(focal_length=24),
            renderer_cfg=IsaacRtxRendererCfg()) if args.video else None
        ground=AssetBaseCfg(prim_path='/World/Ground',spawn=sim_utils.GroundPlaneCfg(
            physics_material=sim_utils.RigidBodyMaterialCfg(static_friction=friction,dynamic_friction=friction)))
        cube=ArticulationCfg(prim_path='{ENV_REGEX_NS}/Cube',
            spawn=sim_utils.UsdFileCfg(usd_path=usd,variants={'Physics':'physx'},activate_contact_sensors=True,
                rigid_props=PhysxRigidBodyCfg(enable_gyroscopic_forces=True,max_angular_velocity=2000),
                articulation_props=PhysxArticulationCfg(enabled_self_collisions=False,
                    solver_position_iteration_count=16,solver_velocity_iteration_count=4,
                    sleep_threshold=0,stabilization_threshold=0)),
            actuators={'wheels':ImplicitActuatorCfg(joint_names_expr=['rotor_.*'],
                joint_effort_limit=p['motor_torque_limit_nm'],stiffness=0,damping=0)})
        contact=ContactSensorCfg(prim_path='{ENV_REGEX_NS}/Cube/Geometry/cube',
            filter_prim_paths_expr=['/World/Ground/CollisionPlane'],track_contact_points=True,
            max_contact_data_count_per_prim=32)

    def tensor(x): return torch.as_tensor(x,device='cuda:0',dtype=torch.float32)
    def rotate(q,v):
        u=q[...,:3];w=q[...,3:4]
        return v+2*torch.cross(u,torch.cross(u,v,dim=-1)+w*v,dim=-1)

    fields=['tilt_x_deg','tilt_y_deg','tilt_total_deg','omega_x_deg_s','omega_y_deg_s','omega_z_deg_s',
        'wheel_x_rpm','wheel_y_rpm','wheel_z_rpm','normal_force_n','slip_speed_m_s','pivot_displacement_mm',
        'motor_x_nm','motor_y_nm','motor_z_nm']
    launcher={'device':'cuda:0','headless':True,'visualizer':[],'multi_gpu':False,
        'enable_cameras':args.video,
        'kit_args':'--/renderer/multiGpu/enabled=false --/renderer/multiGpu/activeCudaGpus=0,'}
    started=time.perf_counter()
    with launch_simulation(PhysxCfg(),launcher):
        sim=sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=dt,device='cuda:0',physics=PhysxCfg(),
            gravity=(0,0,-p['gravity_m_s2'])))
        scene=instantiate(SceneCfg(num_envs=n,env_spacing=1.0,replicate_physics=True))
        sim.reset(); robot=scene['cube']; sensor=scene['contact']
        ids=[robot.joint_names.index(f'rotor_{i}') for i in range(3)]
        initial=[initial_pose(cfg,c) for c in cases]
        pose=tensor(np.stack([v[0] for v in initial])); pose[:,:3]+=scene.env_origins
        direction=tensor(np.stack([v[1] for v in initial])); corner=tensor(np.stack([v[2] for v in initial]))
        robot.write_root_pose_to_sim_index(root_pose=pose)
        velocity=torch.zeros((n,6),device='cuda:0');velocity[:,5]=tensor([c['initial_yaw_rate_rad_s'] for c in cases])
        support_arm=rotate(pose[:,3:],corner)
        velocity[:,:3]=-torch.cross(velocity[:,3:],support_arm,dim=-1)
        robot.write_root_link_velocity_to_sim_index(root_velocity=velocity)
        robot.write_joint_position_to_sim_index(position=torch.zeros_like(robot.data.default_joint_pos.torch))
        robot.write_joint_velocity_to_sim_index(velocity=torch.zeros_like(robot.data.default_joint_vel.torch))
        scene.reset()
        writer=None
        if args.video:
            import imageio.v2 as imageio
            from PIL import Image, ImageDraw
            writer=imageio.get_writer(str(args.output/'eight-corners.mp4'),fps=1/(2*control_dt),codec='libx264',quality=8)
            camera=scene['camera']
            camera.set_world_poses_from_view(scene.env_origins+tensor([.55,-.65,.42]),scene.env_origins+tensor([0,0,.14]))
        # Runtime mass check guards importer defaults before any experiment starts.
        expected=p['frame_mass_kg']+3*p['wheel_mass_kg']
        if not torch.allclose(robot.data.default_mass.torch.sum(-1),tensor(np.full(n,expected)),rtol=1e-5,atol=1e-7):
            raise RuntimeError('Runtime mass differs from frozen model')
        import omni.usd
        physics=omni.usd.get_context().get_stage().GetPrimAtPath('/physicsScene')
        if physics.GetAttribute('physxScene:enableGPUDynamics').Get() is not True:
            raise RuntimeError('GPU dynamics inactive')
        noise=tensor(sensor_noise(cases,cfg,ticks+1))
        measurements=torch.zeros_like(noise)
        trace=torch.zeros((ticks+1,n,len(fields)),device='cuda:0')
        status=torch.zeros(n,dtype=torch.int64,device='cuda:0')
        end_tick=torch.full((n,),ticks,dtype=torch.int64,device='cuda:0')
        missing=torch.zeros(n,device='cuda:0');slipping=missing.clone()
        torque_hits=missing.clone();speed_hits=missing.clone();continuous_hits=missing.clone();integrated=missing.clone()
        K=tensor(payload['compiled']['controller']['K']);yaw=payload['compiled']['controller']['yaw_rate_gain_nm_s']
        delay=cfg.get('sensing',{}).get('control_delay_s',0)/control_dt
        if delay<0: raise ValueError('Negative sensor delay')
        act=cfg.get('actuation',{});peak=min(act.get('peak_torque_nm',p['motor_torque_limit_nm']),p['motor_torque_limit_nm'])
        continuous=act.get('continuous_torque_nm',.04);no_load=act.get('no_load_speed_rad_s',p['wheel_speed_limit_rad_s'])
        if no_load<=0: raise ValueError('Invalid no-load speed')
        contact_slots=torch.arange(32,device='cuda:0')[None,:]
        for tick in range(ticks+1):
            state=robot.data.root_link_pose_w.torch; q=state[:,3:]
            vel=robot.data.root_link_vel_w.torch;omega=vel[:,3:]
            rates=robot.data.joint_vel.torch[:,ids]
            axis=rotate(q,direction)
            tilt=torch.stack((torch.atan2(-axis[:,1],axis[:,2]),torch.atan2(axis[:,0],axis[:,2])),dim=-1)
            total=torch.acos(axis[:,2].clamp(-1,1))*180/np.pi
            momentum=rotate(q,rates*p['wheel_axial_inertia_kg_m2'])
            measurements[tick]=torch.cat((tilt,omega),dim=-1)+noise[tick]
            target=max(0,tick-delay);lo=int(np.floor(target));hi=min(tick,lo+1);fraction=target-lo
            measured=measurements[lo]*(1-fraction)+measurements[hi]*fraction
            x=torch.cat((measured[:,:2],measured[:,2:4],momentum[:,:2]),dim=-1)
            world=torch.cat((-x@K.T,yaw*measured[:,4:5]),dim=-1)
            request=rotate(torch.cat((-q[:,:3],q[:,3:]),dim=-1),world)
            force=sensor.data.net_normal_forces_w.torch[:,:,2].sum(-1)
            raw=sensor.contact_view.get_normal_contact_data(dt=dt)
            forces,points,normals,_,counts,starts=[wp.to_torch(a) for a in raw]
            counts=counts.reshape(n,-1)[:,0].long();starts=starts.reshape(n,-1)[:,0].long()
            if bool((counts>32).any()): raise RuntimeError('Contact buffer capacity exceeded')
            idx=(starts[:,None]+contact_slots).clamp(0,len(points)-1)
            valid=(contact_slots<counts[:,None])&(forces[idx,0]>0)
            arm=points[idx]-state[:,None,:3]
            pv=vel[:,None,:3]+torch.cross(omega[:,None,:].expand_as(arm),arm,dim=-1)
            normal=normals[idx];tangent=pv-normal*(pv*normal).sum(-1,keepdim=True)
            slip=torch.where(valid,tangent.norm(dim=-1),0).amax(-1)
            pivot=state[:,:3]+rotate(q,corner)-scene.env_origins
            drift=pivot[:,:2].norm(dim=-1)*1000
            if tick==0: force=torch.zeros_like(force);slip=torch.zeros_like(slip)
            budget=peak*(1-rates.abs()/no_load).clamp(min=0) if act.get('torque_speed_enabled',True) else torch.full_like(rates,peak)
            applied=request.clamp(-budget,budget)
            blocked=(rates.abs()>=p['wheel_speed_limit_rad_s'])&(applied.sign()==rates.sign())&(applied!=0)
            applied[blocked]=0
            trace[tick]=torch.cat((tilt*180/np.pi,total[:,None],omega*180/np.pi,rates*30/np.pi,
                force[:,None],slip[:,None],drift[:,None],applied),dim=-1)
            active=status==0
            finite=torch.isfinite(trace[tick]).all(-1)&torch.isfinite(state).all(-1)
            missing=torch.where((force<1e-4)&(tick>0),missing+control_dt,0)
            slipping=torch.where(slip>evaluation['slip_stop_speed_m_s'],slipping+control_dt,0)
            failure=torch.zeros_like(status)
            failure[drift>evaluation['pivot_drift_stop_mm']]=3
            failure[slipping>=evaluation['slip_stop_duration_s']]=3
            failure[missing>=evaluation['contact_loss_stop_s']]=2
            failure[total>evaluation['loss_of_balance_deg']]=1
            failure[~finite]=4
            stopped=active&(failure>0);status[stopped]=failure[stopped];end_tick[stopped]=tick
            if args.video and tick%2==0:
                sim.render();camera.update(2*control_dt,force_recompute=True)
                frames=camera.data.output['rgb'].cpu().numpy()
                mosaic=Image.fromarray(np.concatenate([np.concatenate(frames[:4],axis=1),np.concatenate(frames[4:],axis=1)],axis=0))
                draw=ImageDraw.Draw(mosaic)
                for i,c in enumerate(cases):
                    x=(i%4)*320;y=(i//4)*240
                    label=f"corner {c['corner']} | t={tick*control_dt:.2f}s | tilt={float(total[i]):.1f} deg"
                    draw.rectangle((x,y,x+319,y+25),fill=(15,22,32));draw.text((x+5,y+6),label,fill='white')
                    if int(status[i]):draw.text((x+5,y+30),'Stopped: '+['','lost balance','lost contact','slip','invalid'][int(status[i])],fill=(255,70,70))
                writer.append_data(np.asarray(mosaic))
            if not bool(finite.all()): raise RuntimeError('Nonfinite state: batch cannot be used as evidence')
            if tick==ticks: break
            active=status==0
            for _ in range(substeps):
                rates=robot.data.joint_vel.torch[:,ids]
                budget=peak*(1-rates.abs()/no_load).clamp(min=0) if act.get('torque_speed_enabled',True) else torch.full_like(rates,peak)
                applied=request.clamp(-budget,budget)
                blocked=(rates.abs()>=p['wheel_speed_limit_rad_s'])&(applied.sign()==rates.sign())&(applied!=0)
                applied[blocked]=0
                torque_hits+=((request-applied).abs()>1e-7).any(-1)&active
                speed_hits+=blocked.any(-1)&active
                continuous_hits+=(applied.abs()>continuous+1e-7).any(-1)&active
                integrated+=active
                applied[~active]=0
                robot.actuators.target_command.set_effort_index(value=applied,joint_ids=ids)
                scene.write_data_to_sim();sim.step(render=False);scene.update(dt)
            if tick%100==0: print(f'tick {tick}/{ticks}; active {int(active.sum())}/{n}',flush=True)
        arrays=trace.cpu().numpy();ends=end_tick.cpu().numpy();statuses=status.cpu().numpy()
        if writer is not None:writer.close()
        hits=torch.stack((torque_hits,speed_hits,continuous_hits,integrated),dim=-1).cpu().numpy()
        np.savez_compressed(args.output/'telemetry.npz',values=arrays,time_s=np.arange(ticks+1)*control_dt,
            fields=np.array(fields),end_tick=ends,status=statuses)
        summaries=[]
        for i,c in enumerate(cases):
            a=arrays[:ends[i]+1,i];last=a[max(0,len(a)-1-int(1/control_dt)):]
            summaries.append({**c,'status':['completed','lost_balance','lost_contact','excessive_slip','numerical_failure'][statuses[i]],
                'simulated_duration_s':float(ends[i]*control_dt),'peak_tilt_deg':float(a[:,2].max()),
                'final_1s_tilt_rms_deg':float(np.sqrt(np.mean(last[:,2]**2))),
                'final_1s_yaw_rate_rms_deg_s':float(np.sqrt(np.mean(last[:,5]**2))),
                'peak_wheel_rpm':float(np.abs(a[:,6:9]).max()),'peak_motor_torque_nm':float(np.abs(a[:,12:15]).max()),
                'peak_contact_force_n':float(a[:,9].max()),'contact_fraction':float(np.mean(a[1:,9]>1e-4)) if len(a)>1 else 0.,
                'peak_slip_speed_m_s':float(a[:,10].max()),'peak_pivot_displacement_mm':float(a[:,11].max()),
                'torque_limited_fraction':float(hits[i,0]/max(1,hits[i,3])),
                'speed_governor_fraction':float(hits[i,1]/max(1,hits[i,3])),
                'continuous_torque_exceeded_fraction':float(hits[i,2]/max(1,hits[i,3]))})
        result={'backend':'isaacsim_physx','gpu_uuid':gpu,'trial_count':n,'wall_time_s':time.perf_counter()-started,
            'input_digest':payload['compiled']['input_digest'],'cases_sha256':hashlib.sha256(args.cases.read_bytes()).hexdigest(),
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'physics_timestep_s':dt,'control_period_s':control_dt,'physical_verified':False,
            'agreement_state':'not_run','summaries':summaries}
        (args.output/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        print('Completed',n,'trials',flush=True)


if __name__ == "__main__":
    main()
