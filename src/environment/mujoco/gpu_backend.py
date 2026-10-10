"""Batched MJX/JAX port of S2 with an explicit accelerator preflight.

MuJoCo and mujoco-mjx must both be 3.3.7. The default execution requires an
actual GPU; CPU is permitted only when explicitly requested for validation.
The physics, sensors and fixed controller retain the S2 assumptions. No measured
motor, IMU, thermal or contact calibration is implied by accelerator execution.
"""
from __future__ import annotations

from functools import lru_cache
import importlib.metadata
import time
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from .contact import CONTACT_DEFAULTS, build_contact_xml
from .model import equilibrium_rotation, quat

SUPPORTED_VERSION = "3.3.7"
ROW_FIELDS = ["time_s", "tilt_x_deg", "tilt_y_deg", "tilt_total_deg",
              "omega_x_deg_s", "omega_y_deg_s", "omega_z_deg_s",
              "wheel_x_rpm", "wheel_y_rpm", "wheel_z_rpm",
              "motor_x_nm", "motor_y_nm", "motor_z_nm", "contact_count",
              "normal_force_n", "slip_speed_m_s", "pivot_displacement_mm",
              "absolute_mechanical_work_j", "measured_tilt_x_deg", "measured_tilt_y_deg",
              "torque_limited", "speed_governor_active", "continuous_torque_exceeded",
              "torque_budget_x_nm", "torque_budget_y_nm", "torque_budget_z_nm"]
SUMMARY_FIELDS = ["simulated_duration_s", "initial_tilt_deg", "peak_tilt_deg",
                  "final_1s_tilt_rms_deg", "final_1s_yaw_rate_rms_deg_s",
                  "peak_wheel_rpm", "peak_motor_torque_nm", "peak_contact_force_n",
                  "contact_fraction", "peak_slip_speed_m_s", "peak_pivot_displacement_mm",
                  "final_pivot_displacement_mm", "torque_limited_fraction",
                  "speed_governor_fraction", "continuous_torque_exceeded_fraction",
                  "absolute_mechanical_work_j"]
STATUS_NAMES = {1: "completed", 2: "lost_balance", 3: "lost_contact",
                4: "excessive_slip", 5: "numerical_failure"}
_EXECUTABLES = {}


def _imports():
    try:
        import jax
        import jax.numpy as jnp
        from mujoco import mjx
        from mujoco.mjx._src import support
    except ImportError as error:
        raise RuntimeError("The MJX environment is missing. Install the pinned GPU/validation requirements and use that Python interpreter.") from error
    version = importlib.metadata.version("mujoco-mjx")
    if mujoco.__version__ != SUPPORTED_VERSION or version != SUPPORTED_VERSION:
        raise RuntimeError(f"Expected matching mujoco/mujoco-mjx {SUPPORTED_VERSION}; got {mujoco.__version__}/{version}")
    return jax, jnp, mjx, support


def device_inventory(require_gpu=True):
    """Fail before compilation if acceleration was requested but is unavailable."""
    jax, _, _, _ = _imports()
    devices = jax.devices()
    gpu = [d for d in devices if d.platform == "gpu"]
    if require_gpu and not gpu:
        raise RuntimeError("GPU execution required, but JAX found no GPU. No CPU fallback was run. Check NVIDIA driver, CUDA-enabled jaxlib and CUDA_VISIBLE_DEVICES.")
    selected = gpu[0] if gpu else devices[0]
    return {"devices": [{"id": int(d.id), "platform": d.platform,
                         "device_kind": d.device_kind} for d in devices],
            "selected_device": str(selected), "accelerated": selected.platform == "gpu",
            "jax_version": jax.__version__, "mujoco_version": mujoco.__version__,
            "mjx_version": importlib.metadata.version("mujoco-mjx")}, selected


def physics_xml(cfg):
    """Strip zero-mass visual geoms; keep the identical S2 inertials and contacts."""
    root = ET.fromstring(build_contact_xml(cfg))
    # Otherwise the decorative 512x512 checker texture is copied once per world
    # even though it is never read by the physics kernel.
    for tag in ("asset", "visual"):
        element = root.find(tag)
        if element is not None:
            root.remove(element)
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "geom" and child.get("contype", "0") != "1":
                parent.remove(child)
            elif child.tag in ("light", "camera", "site"):
                parent.remove(child)
            elif child.tag == "geom":
                child.attrib.pop("material", None)
    return ET.tostring(root, encoding="unicode")


def _noise_samples(cfg, case, length):
    sensing = cfg.get("sensing", {})
    seed = int(case.get("seed", sensing.get("seed", 0)))
    rng = np.random.default_rng(seed)
    tilt = np.deg2rad(sensing.get("tilt_noise_std_deg", 0))
    gyro = np.deg2rad(sensing.get("gyro_noise_std_deg_s", 0))
    # The call order matches SensorPipeline.sample, including the held initial sample.
    return np.asarray([np.r_[rng.normal(0, tilt, 2), rng.normal(0, gyro, 3)] for _ in range(length)])


def _controller_values(controller):
    if hasattr(controller, "k"):
        return np.asarray(controller.k), float(controller.yaw_gain)
    gain = controller.get("K", controller.get("k"))
    yaw = controller.get("yaw_rate_gain_nm_s", controller.get("yaw_gain"))
    if gain is None or yaw is None:
        raise ValueError("Pass a fixed Regulator or a dict containing K and yaw_rate_gain_nm_s")
    return np.asarray(gain), float(yaw)


@lru_cache(maxsize=32)
def _runner(substeps, control_steps, history_size, cube, wheel_dofs, wheel_qpos):
    jax, jp, mjx, support = _imports()
    wd, wq = jp.array(wheel_dofs), jp.array(wheel_qpos)
    deg = 180 / jp.pi

    def torque_limit(requested, rates, parameters):
        # Parameters: wheel inertia, peak torque, no-load speed, speed ceiling,
        # continuous torque, envelope flag, control period, delay integer/fraction,
        # loss tilt, contact/slip hold, slip speed, drift, target steps, control flag.
        budget = parameters[1] * jp.where(parameters[5] > .5,
                                          jp.maximum(0, 1-jp.abs(rates)/parameters[2]), 1)
        budget = jp.broadcast_to(budget, (3,))
        applied = jp.clip(requested, -budget, budget)
        blocked = (jp.abs(rates)>=parameters[3]) & (jp.sign(applied)==jp.sign(rates)) & (applied!=0)
        return jp.where(blocked, 0, applied), budget, blocked

    def observe(model, data):
        rotation = data.xmat[cube]
        direction = rotation @ (jp.ones(3)/jp.sqrt(3.0))
        tilt = jp.array([jp.arctan2(-direction[1], direction[2]), jp.arctan2(direction[0], direction[2])])
        # acos loses sub-0.02 degree resolution near vertical in float32.
        # atan2 is geometrically equivalent and retains small-angle observability.
        angle = jp.arctan2(jp.linalg.norm(direction[:2]), direction[2])*deg
        # Free-joint angular velocity is body local; its translation is world local.
        omega = rotation @ data.qvel[3:6]
        wheels = data.qvel[wd]
        forces, indices = support.contact_force_dim(model, data, 6)
        normal_force = jp.maximum(forces[:, 0], 0)
        points = data._impl.contact.pos[indices]
        normals = data._impl.contact.frame[indices, 0, :]
        velocity = data.qvel[:3] + jp.cross(omega[None, :], points-data.xpos[cube])
        tangent = velocity-jp.sum(velocity*normals, axis=1)[:, None]*normals
        loaded = normal_force>1e-8
        slip = jp.max(jp.where(loaded, jp.linalg.norm(tangent, axis=1), 0))
        return rotation, tilt, angle, omega, wheels, jp.sum(loaded), jp.sum(normal_force), slip, jp.linalg.norm(data.xpos[cube, :2])*1000

    def trajectory(model, initial_data, parameters, noises, external, gain, yaw_gain):
        # put_data uses int32 contact indices; x64 MJX forward emits int64 indices.
        # Normalize once before scan so its carry has a stable index dtype.
        initial_data = mjx.forward(model, initial_data)
        scalar_zero = jp.array(0.0, dtype=parameters.dtype)
        initial = (initial_data, jp.zeros((history_size, 5), dtype=parameters.dtype),
                   jp.array(True), jp.array(0), jp.array(-1), scalar_zero, scalar_zero,
                   scalar_zero, jp.zeros(4, dtype=parameters.dtype))

        def control_tick(carry, tick_inputs):
            data, history, alive, status, stop, no_contact, slip_time, work, counts = carry
            tick, noise, pulse = tick_inputs
            data = mjx.forward(model, data)
            rotation, tilt, angle, omega, wheels, ncontact, force, slip, drift = observe(model, data)
            sample = jp.concatenate((tilt, omega))+noise
            history = jp.where(tick==0, jp.broadcast_to(sample, history.shape),
                               jp.concatenate((history[1:], sample[None]), axis=0))
            delay = parameters[7].astype(jp.int32)
            fraction = parameters[8]
            measured = history[history_size-1-delay]*(1-fraction)+history[history_size-2-delay]*fraction
            momentum = rotation @ (parameters[0]*wheels)
            state = jp.concatenate((measured[:2], measured[2:4], momentum[:2]))
            command = rotation.T @ jp.concatenate((-gain @ state, (yaw_gain*measured[4])[None]))
            command = jp.where(parameters[15]>.5, command, jp.zeros(3))
            applied, budget, blocked = torque_limit(command, wheels, parameters)
            limited = jp.any(jp.abs(command-applied)>1e-12)
            continuous = jp.any(jp.abs(applied)>parameters[4]+1e-12)
            finite = jp.all(jp.isfinite(data.qpos)) & jp.all(jp.isfinite(data.qvel))
            no_contact = jp.where((tick>0) & (force<1e-4), no_contact+parameters[6], 0)
            slip_time = jp.where(slip>parameters[12], slip_time+parameters[6], 0)
            reason = jp.where(~finite, 5, jp.where(angle>parameters[9], 2,
                     jp.where(no_contact>=parameters[10], 3,
                     jp.where((slip_time>=parameters[11]) | (drift>parameters[13]), 4,
                     jp.where(tick>=parameters[14], 1, 0)))))
            finished = alive & (reason!=0)
            stop = jp.where(finished, tick, stop)
            status = jp.where(finished, reason, status)
            can_advance = alive & (reason==0)
            row = jp.concatenate((jp.array([tick*parameters[6]]), tilt*deg, angle[None], omega*deg,
                                  wheels*30/jp.pi, applied, jp.array([ncontact, force, slip, drift, work]),
                                  measured[:2]*deg, jp.array([limited, jp.any(blocked), continuous]), budget))

            def physics_tick(state, _):
                current, delta_work, delta_counts = state
                actual, _, governor = torque_limit(command, current.qvel[wd], parameters)
                limited_now = jp.any(jp.abs(command-actual)>1e-12)
                continuous_now = jp.any(jp.abs(actual)>parameters[4]+1e-12)
                force_applied = jp.zeros_like(current.xfrc_applied).at[cube, 3:].set(pulse)
                next_data = mjx.step(model, current.replace(ctrl=actual, xfrc_applied=force_applied))
                delta_work += jp.sum(jp.abs(actual*(next_data.qpos[wq]-current.qpos[wq])))
                delta_counts += jp.array([limited_now, jp.any(governor), continuous_now, 1], dtype=parameters.dtype)
                return (next_data, delta_work, delta_counts), None

            advanced, _ = jax.lax.scan(physics_tick, (data, scalar_zero, jp.zeros(4, dtype=parameters.dtype)), None, length=substeps)
            next_data = jax.tree_util.tree_map(lambda old, new: jp.where(can_advance, new, old), data, advanced[0])
            work += jp.where(can_advance, advanced[1], 0)
            counts += jp.where(can_advance, advanced[2], 0)
            return (next_data, history, can_advance, status, stop, no_contact, slip_time, work, counts), (row, alive)

        final, (rows, valid) = jax.lax.scan(control_tick, initial,
                                           (jp.arange(control_steps+1), noises, external))
        stop = final[4]
        end_time = rows[stop, 0]
        final_window = valid & (rows[:, 0]>=end_time-1)
        denominator = jp.maximum(jp.sum(final_window), 1)
        contact_samples = valid & (jp.arange(control_steps+1)>0)
        maximum = lambda index: jp.max(jp.where(valid, rows[:, index], 0))
        counts = final[8]
        interval_count = jp.maximum(counts[3], 1)
        summary = jp.array([end_time, rows[0, 3], maximum(3),
                           jp.sqrt(jp.sum(jp.where(final_window, rows[:, 3]**2, 0))/denominator),
                           jp.sqrt(jp.sum(jp.where(final_window, rows[:, 6]**2, 0))/denominator),
                           jp.max(jp.where(valid[:, None], jp.abs(rows[:, 7:10]), 0)),
                           jp.max(jp.where(valid[:, None], jp.abs(rows[:, 10:13]), 0)),
                           maximum(14), jp.sum(contact_samples & (rows[:, 14]>1e-4))/jp.maximum(jp.sum(contact_samples), 1),
                           maximum(15), maximum(16), rows[stop, 16],
                           counts[0]/interval_count, counts[1]/interval_count, counts[2]/interval_count, final[7]])
        return summary, final[3], stop, rows

    return jax.jit(jax.vmap(trajectory, in_axes=(0, 0, 0, 0, 0, None, None)))


def run_batch(configs, cases, controller, require_gpu=True, duration_s=None, selected_indices=(), precision="float32"):
    """Simulate paired configuration/case arrays on one visible device.

    Cases are paired 1:1 with configurations; expand candidate × domain × seed in
    the caller. Topology, physics timestep and control period must match. Candidate
    masses/inertias/geometry/friction are stacked dynamic model arrays. Compilation
    is reused for identical topology/batch/horizon/history/precision shapes.
    """
    if not configs or len(configs)!=len(cases):
        raise ValueError("configs and cases must be nonempty lists of the same length")
    if precision not in ("float32", "float64"):
        raise ValueError("precision must be float32 or float64")
    jax, jp, mjx, _ = _imports()
    metadata, device = device_inventory(require_gpu)
    # MJX creates intermediate arrays according to this global JAX setting. Mixed
    # precision in one process is therefore sequential; GPU workers use float32.
    jax.config.update("jax_enable_x64", precision=="float64")
    dtype = np.float64 if precision=="float64" else np.float32
    dt = float(configs[0]["physics"]["control_period_s"])
    timestep = float(configs[0]["physics"]["timestep_s"])
    substeps = round(dt/timestep)
    if not np.isclose(dt/timestep, substeps):
        raise ValueError("control period must be an integer multiple of physics timestep")
    durations = [float(duration_s if duration_s is not None else case.get("duration_s", cfg["evaluation"]["duration_s"]))
                 for cfg, case in zip(configs, cases)]
    if min(durations)<0:
        raise ValueError("duration_s must be nonnegative")
    steps = max(round(value/dt) for value in durations)
    delays = [float(cfg.get("sensing", {}).get("control_delay_s", 0))/dt for cfg in configs]
    if min(delays)<0:
        raise ValueError("control_delay_s cannot be negative")
    history_size = int(np.ceil(max(delays)))+2
    selected_indices = tuple(int(i) for i in selected_indices)
    if any(i<0 or i>=len(cases) for i in selected_indices):
        raise IndexError("selected_indices outside batch")
    preparation_started = time.perf_counter()
    cpu_models, models, data, parameters, noises, disturbances = [], [], [], [], [], []
    model_tree = None
    model_cache = {}
    converted_model_cache, noise_cache = {}, {}
    for cfg, case, duration, lag in zip(configs, cases, durations, delays):
        if cfg["physics"]["timestep_s"]!=timestep or cfg["physics"]["control_period_s"]!=dt:
            raise ValueError("Group different timesteps/control periods into separate batches")
        # Seeds and initial conditions share a compiled host model. Different
        # physical domains are compiled once to preserve MuJoCo-derived inertials.
        xml = physics_xml(cfg)
        if xml not in model_cache:
            model_cache[xml] = mujoco.MjModel.from_xml_string(xml)
        model = model_cache[xml]
        datum = mujoco.MjData(model)
        tilt = np.deg2rad(case.get("initial_tilt_deg", [0, 0]))
        rotation = Rotation.from_rotvec([tilt[0], tilt[1], 0]).as_matrix() @ equilibrium_rotation("vertex")
        radius = cfg.get("contact", {}).get("corner_radius_m", CONTACT_DEFAULTS["corner_radius_m"])
        datum.qpos[:3] = [0, 0, radius]
        datum.qpos[3:7] = quat(rotation)
        datum.qvel[3:6] = rotation.T @ np.array([0, 0, case.get("initial_yaw_rate_rad_s", 0)])
        mujoco.mj_forward(model, datum)
        converted_data = mjx.put_data(model, datum, device=device, impl="jax")
        # In MJX 3.3.7, geom_aabb is unused by the JAX backend and
        # geom_rbound_hfield is read only for height-field collisions. They are
        # nevertheless static numpy fields and would split batches by sphere
        # radius. This guarded plane/sphere model can canonicalize those unused
        # fields; dynamic geom_size/geom_pos/geom_rbound keep the real dimensions.
        if model.ngeom!=9 or not np.all(np.isin(model.geom_type, [mujoco.mjtGeom.mjGEOM_PLANE, mujoco.mjtGeom.mjGEOM_SPHERE])):
            raise ValueError("GPU S2 port supports only the floor and eight sphere corners")
        if xml not in converted_model_cache:
            converted_model = mjx.put_model(model, device=device, impl="jax")
            converted_model_cache[xml] = converted_model.replace(
                geom_aabb=np.zeros_like(converted_model.geom_aabb),
                _impl=converted_model._impl.replace(geom_rbound_hfield=np.zeros_like(converted_model._impl.geom_rbound_hfield)))
        converted_model = converted_model_cache[xml]
        tree = jax.tree_util.tree_structure(converted_model)
        if model_tree is not None and tree!=model_tree:
            raise ValueError("Candidate changes MJX static topology; group it in a separate batch")
        model_tree = tree
        cpu_models.append(model)
        models.append(converted_model)
        data.append(converted_data)
        p, a, e = cfg["physics"], cfg.get("actuation", {}), cfg["evaluation"]
        no_load = float(a.get("no_load_speed_rad_s", p["wheel_speed_limit_rad_s"]))
        if no_load<=0:
            raise ValueError("no_load_speed_rad_s must be positive")
        integer_lag = int(np.floor(lag+1e-12))
        fraction = max(0.0, lag-integer_lag)
        parameters.append([p["wheel_axial_inertia_kg_m2"], min(a.get("peak_torque_nm", p["motor_torque_limit_nm"]), p["motor_torque_limit_nm"]),
                           no_load, p["wheel_speed_limit_rad_s"], a.get("continuous_torque_nm", .04), a.get("torque_speed_enabled", True),
                           dt, integer_lag, fraction, e["loss_of_balance_deg"], e.get("contact_loss_hold_s", .10), e.get("slip_hold_s", .15),
                           e.get("slip_speed_limit_m_s", .05), e.get("max_pivot_displacement_mm", 30), round(duration/dt), case.get("control", True)])
        sensing = cfg.get("sensing", {})
        noise_key = (int(case.get("seed", sensing.get("seed", 0))),
                     sensing.get("tilt_noise_std_deg", 0), sensing.get("gyro_noise_std_deg_s", 0))
        if noise_key not in noise_cache:
            noise_cache[noise_key] = _noise_samples(cfg, case, steps+1)
        noises.append(noise_cache[noise_key])
        pulses = np.zeros((steps+1, 3))
        for tick in range(steps+1):
            t = tick*dt
            for pulse in case.get("disturbances", []):
                if pulse["start_s"]<=t+1e-9<pulse["start_s"]+pulse["duration_s"]-1e-9:
                    pulses[tick] += pulse["torque_world_nm"]
        disturbances.append(pulses)
    # Static fields remain a shared treedef; every dynamic leaf gains a batch axis.
    stack = lambda *values: jp.stack(values)
    cast = lambda x: x.astype(dtype) if jp.issubdtype(x.dtype, jp.floating) else x
    model_batch = jax.tree_util.tree_map(cast, jax.tree_util.tree_map(stack, *models))
    data_batch = jax.tree_util.tree_map(cast, jax.tree_util.tree_map(stack, *data))
    gain, yaw = _controller_values(controller)
    if gain.shape!=(2, 6):
        raise ValueError("Vertex controller K must have shape (2,6)")
    args = (model_batch, data_batch, jp.asarray(parameters, dtype=dtype),
            jp.asarray(noises, dtype=dtype), jp.asarray(disturbances, dtype=dtype),
            jp.asarray(gain, dtype=dtype), jp.asarray(yaw, dtype=dtype))
    cube = mujoco.mj_name2id(cpu_models[0], mujoco.mjtObj.mjOBJ_BODY, "cube")
    rotor_ids = [mujoco.mj_name2id(cpu_models[0], mujoco.mjtObj.mjOBJ_JOINT, f"rotor_{i}") for i in range(3)]
    wheel_dofs = tuple(int(x) for x in cpu_models[0].jnt_dofadr[rotor_ids])
    wheel_qpos = tuple(int(x) for x in cpu_models[0].jnt_qposadr[rotor_ids])
    runner = _runner(substeps, steps, history_size, cube, wheel_dofs, wheel_qpos)
    key = (model_tree, len(cases), steps, history_size, substeps, precision, str(device))
    jax.block_until_ready(args)
    preparation_s = time.perf_counter()-preparation_started
    compile_started = time.perf_counter()
    cache_hit = key in _EXECUTABLES
    if not cache_hit:
        _EXECUTABLES[key] = runner.lower(*args).compile()
    compile_s = time.perf_counter()-compile_started
    execute_started = time.perf_counter()
    with jax.default_device(device):
        summaries_array, statuses, stops, all_rows = _EXECUTABLES[key](*args)
        summaries_array.block_until_ready()
    execute_s = time.perf_counter()-execute_started
    summaries_array = np.asarray(summaries_array)
    statuses, stops = np.asarray(statuses), np.asarray(stops)
    if not np.isfinite(summaries_array).all():
        raise RuntimeError("Non-finite MJX output: batch is invalid and cannot pass screening")
    summaries = []
    for i, (cfg, case) in enumerate(zip(configs, cases)):
        summaries.append({"id": case.get("id", str(i)), "label": case.get("label", ""),
                          "mode": "vertex_contact_mjx", "control": case.get("control", True),
                          "status": STATUS_NAMES[int(statuses[i])], "requested_duration_s": durations[i],
                          **dict(zip(SUMMARY_FIELDS, map(float, summaries_array[i]))),
                          "sensor_delay_s": cfg.get("sensing", {}).get("control_delay_s", 0),
                          "seed": int(case.get("seed", cfg.get("sensing", {}).get("seed", 0))),
                          "note": "MJX/JAX S2近似。固定SIゲイン、理想エンコーダ/座標変換、真値＋雑音/遅延。実機成功・測定済みモデルを意味しない。"})
    selected = {}
    for index in selected_indices:
        rows = np.asarray(all_rows[index, :int(stops[index])+1])
        if not np.isfinite(rows).all():
            raise RuntimeError(f"Non-finite rows for batch index {index}")
        selected[str(index)] = [dict(zip(ROW_FIELDS, map(float, row))) for row in rows]
    metadata.update({"backend": "mujoco-mjx/jax", "precision": precision,
                     "preparation_wall_time_s": preparation_s, "compile_wall_time_s": compile_s,
                     "execution_wall_time_s": execute_s, "compile_cache_hit": cache_hit,
                     "batch_size": len(cases), "physics_timestep_s": timestep, "control_period_s": dt,
                     "notes": "CPU validation is explicitly opt-in; accelerated=false is never a GPU benchmark. Contact count denotes load-bearing contacts; force/slip use condim6 solver contacts. Zero-mass visual geoms are removed without changing inertia or collision shape."})
    return {"metadata": metadata, "summaries": summaries, "selected_rows": selected}
