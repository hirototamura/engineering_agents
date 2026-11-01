"""S2: unconstrained cube with approximate spherical corner / floor contacts.

The shape, friction, motor envelope and sensor noise are unmeasured assumptions.
This model is useful for finding sensitivity and failures; completing a run does
not establish that the printed hardware will balance.
"""
from __future__ import annotations

import copy
from collections import deque
import time
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from .control import Regulator
from .model import Plant, build_xml, equilibrium_rotation, fmt, quat


CONTACT_DEFAULTS = {
    "corner_radius_m": .004, "sliding_friction": .7,
    "torsional_friction_m": .0001, "rolling_friction_m": .00005,
    "solref": [.01, 1.0], "solimp": [.95, .99, .001],
}


def build_contact_xml(cfg):
    """Replace the ideal pivot by six free DOFs and eight massless corner spheres."""
    frame_com = np.asarray(cfg["physics"]["frame_com_fraction"], dtype=float)
    if frame_com.shape != (3,) or not np.allclose(frame_com, frame_com[0], atol=1e-12, rtol=0):
        raise ValueError("S2 currently supports only a symmetric frame COM on the cube body diagonal; asymmetric frame_com_fraction requires recalculating the equilibrium and tilt observation")
    contact = {**CONTACT_DEFAULTS, **cfg.get("contact", {})}
    radius = float(contact["corner_radius_m"])
    if not 0 < radius < cfg["physics"]["cube_side_m"] / 4:
        raise ValueError("corner_radius_m must be positive and smaller than side/4")
    root = ET.fromstring(build_xml(cfg, "vertex", free=True))
    root.set("model", "reaction_wheel_cube_s2_corner_contact")
    root.find("option").set("integrator", "implicitfast")
    root.find("option").set("iterations", "100")
    root.find("option").set("tolerance", "1e-10")
    world = root.find("worldbody")
    world.remove(world.find("geom[@name='ideal_pivot']"))
    floor = world.find("geom[@name='visual_floor']")
    floor.set("name", "floor_contact")
    floor.set("contype", "1")
    floor.set("conaffinity", "1")
    body = world.find("body[@name='cube']")
    body.set("pos", fmt([0, 0, radius]))
    friction = fmt([contact["sliding_friction"], contact["torsional_friction_m"], contact["rolling_friction_m"]])
    floor.set("friction", friction)
    side = cfg["physics"]["cube_side_m"]
    for x in (0, side):
        for y in (0, side):
            for z in (0, side):
                ET.SubElement(body, "geom", name=f"corner_{int(x>0)}{int(y>0)}{int(z>0)}",
                              type="sphere", pos=fmt([x, y, z]), size=str(radius), mass="0",
                              contype="1", conaffinity="1", condim="6", friction=friction,
                              solref=fmt(contact["solref"]), solimp=fmt(contact["solimp"]),
                              rgba=".12 .9 .72 1")
    # The model's inertials still come from the configured frame and wheel masses.
    peak = cfg.get("actuation", {}).get("peak_torque_nm", cfg["physics"]["motor_torque_limit_nm"])
    limit = min(peak, cfg["physics"]["motor_torque_limit_nm"])
    for motor in root.findall("actuator/motor"):
        motor.set("ctrlrange", fmt([-limit, limit]))
    return ET.tostring(root, encoding="unicode")


class ContactPlant(Plant):
    def __init__(self, cfg):
        self.cfg = copy.deepcopy(cfg)
        self.mode = "vertex"
        self.xml = build_contact_xml(cfg)
        self.model = mujoco.MjModel.from_xml_string(self.xml)
        self.data = mujoco.MjData(self.model)
        self.body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "cube")
        ids = [mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, f"rotor_{i}") for i in range(3)]
        self.wheel_dofs = self.model.jnt_dofadr[ids]
        self.wheel_qpos = self.model.jnt_qposadr[ids]
        self.r0 = equilibrium_rotation("vertex")
        self.wheel_j = cfg["physics"]["wheel_axial_inertia_kg_m2"]
        n = cfg["physics"]["control_period_s"] / cfg["physics"]["timestep_s"]
        if not np.isclose(n, round(n)):
            raise ValueError("control period must be an integer multiple of timestep")
        self.substeps = round(n)
        self.set_state()

    def set_state(self, state=None, tilt_deg=None, yaw_rate=0):
        mujoco.mj_resetData(self.model, self.data)
        if state is None:
            state = np.r_[np.deg2rad([0, 0] if tilt_deg is None else tilt_deg), 0, 0, 0, 0]
        rotation = Rotation.from_rotvec([state[0], state[1], 0]).as_matrix() @ self.r0
        radius = self.cfg.get("contact", {}).get("corner_radius_m", CONTACT_DEFAULTS["corner_radius_m"])
        self.data.qpos[:3] = [0, 0, radius]
        self.data.qpos[3:7] = quat(rotation)
        self.data.qvel[3:6] = rotation.T @ np.array([state[2], state[3], yaw_rate])
        self.data.qvel[self.wheel_dofs] = rotation.T @ np.array([state[4], state[5], 0]) / self.wheel_j
        mujoco.mj_forward(self.model, self.data)

    def contact_observation(self):
        force, slip, count = 0.0, 0.0, 0
        for i in range(self.data.ncon):
            contact = self.data.contact[i]
            # Skip inactive candidate contacts outside the solver's contact margin.
            if contact.efc_address < 0:
                continue
            bodies = self.model.geom_bodyid[[contact.geom1, contact.geom2]]
            if self.body not in bodies:
                continue
            wrench = np.zeros(6)
            mujoco.mj_contactForce(self.model, self.data, i, wrench)
            force += max(0.0, float(wrench[0]))
            count += 1
            # Contact-point velocity on the cube, projected into the floor tangent.
            jacobian = np.zeros((3, self.model.nv))
            mujoco.mj_jac(self.model, self.data, jacobian, None, contact.pos, self.body)
            point_velocity = jacobian @ self.data.qvel
            normal = contact.frame[:3]
            tangent = point_velocity - normal * (normal @ point_velocity)
            slip = max(slip, float(np.linalg.norm(tangent)))
        return {"contact_count": count, "normal_force_n": force,
                "slip_speed_m_s": slip,
                "pivot_displacement_mm": float(np.linalg.norm(self.data.xpos[self.body, :2])*1000)}


class SensorPipeline:
    """Sample noisy tilt/gyro, then apply a timestamped observation delay.

    Before enough history exists, the initial sampled observation is held. Rotor
    rate measurements remain ideal encoder values; their calibration is pending.
    """
    def __init__(self, sensing):
        self.delay = float(sensing.get("control_delay_s", 0))
        if self.delay < 0:
            raise ValueError("control_delay_s cannot be negative")
        self.tilt_std = np.deg2rad(sensing.get("tilt_noise_std_deg", 0))
        self.gyro_std = np.deg2rad(sensing.get("gyro_noise_std_deg_s", 0))
        self.rng = np.random.default_rng(sensing.get("seed", 0))
        self.history = deque()

    def sample(self, timestamp, tilt, omega):
        measured = np.r_[np.asarray(tilt)+self.rng.normal(0, self.tilt_std, 2),
                         np.asarray(omega)+self.rng.normal(0, self.gyro_std, 3)]
        self.history.append((float(timestamp), measured))
        target = timestamp-self.delay
        while len(self.history)>2 and self.history[1][0] <= target:
            self.history.popleft()
        if target <= self.history[0][0] or len(self.history)==1:
            return self.history[0][1].copy()
        t0, a = self.history[0]
        t1, b = self.history[1]
        fraction = np.clip((target-t0)/(t1-t0), 0, 1)
        return a*(1-fraction)+b*fraction


def limit_motor_torque(cfg, requested, wheel_rates):
    """Uncalibrated symmetric linear torque-speed envelope (not a motor model).

    The envelope conservatively limits both acceleration and braking. It does not
    predict regenerative braking, supply current, thermal rise or voltage sag.
    """
    actuation = cfg.get("actuation", {})
    peak = min(float(actuation.get("peak_torque_nm", cfg["physics"]["motor_torque_limit_nm"])),
               cfg["physics"]["motor_torque_limit_nm"])
    speed_limit = cfg["physics"]["wheel_speed_limit_rad_s"]
    budget = np.full(3, peak)
    if actuation.get("torque_speed_enabled", True):
        no_load = float(actuation.get("no_load_speed_rad_s", speed_limit))
        if no_load <= 0:
            raise ValueError("no_load_speed_rad_s must be positive")
        budget *= np.maximum(0, 1-np.abs(wheel_rates)/no_load)
    applied = np.clip(requested, -budget, budget)
    blocked = (np.abs(wheel_rates)>=speed_limit) & (np.sign(applied)==np.sign(wheel_rates)) & (applied!=0)
    applied[blocked] = 0
    return applied, budget, blocked


def contact_stop_limits(evaluation):
    """Resolve the canonical SSOT fields shared by native CPU and MJX."""
    return (evaluation.get("contact_loss_stop_s", .10),
            evaluation.get("slip_stop_speed_m_s", .05),
            evaluation.get("slip_stop_duration_s", .15),
            evaluation.get("pivot_drift_stop_mm", 30.0))


def simulate_contact(cfg, case, regulator=None):
    """Run one S2 case; return JSON-serializable summary and sampled data rows.

    Pass a Regulator computed from a nominal configuration for fair comparisons
    across candidate physics and test cases. This function never retunes that gain.
    """
    started = time.perf_counter()
    plant = ContactPlant(cfg)
    regulator = Regulator(cfg, "vertex") if regulator is None else regulator
    plant.set_state(tilt_deg=case.get("initial_tilt_deg", [0, 0]), yaw_rate=case.get("initial_yaw_rate_rad_s", 0))
    pipeline = SensorPipeline({**cfg.get("sensing", {}), "seed": case.get("seed", cfg.get("sensing", {}).get("seed", 0))})
    evaluation = cfg["evaluation"]
    duration = float(case.get("duration_s", evaluation["duration_s"]))
    dt = cfg["physics"]["control_period_s"]
    if duration < 0:
        raise ValueError("duration_s cannot be negative")
    rows, status, work = [], "completed", 0.0
    missing_contact_s = 0.0
    excessive_slip_s = 0.0
    contact_loss_hold, slip_limit, slip_hold, max_drift = contact_stop_limits(evaluation)
    torque_hits, speed_hits, continuous_hits = 0, 0, 0
    integrated_steps = 0
    true_steps = round(duration/dt)
    for step in range(true_steps+1):
        if not np.isfinite(plant.data.qpos).all() or not np.isfinite(plant.data.qvel).all():
            status = "numerical_failure"
            break
        observation = plant.observe()
        t = float(plant.data.time)
        measured = pipeline.sample(t, observation["tilt"], observation["omega"])
        state = np.r_[measured[:2], measured[2:4], observation["momentum"][:2]]
        torque_world = np.r_[-regulator.k@state, regulator.yaw_gain*measured[4]]
        requested = plant.motor_command(torque_world) if case.get("control", True) else np.zeros(3)
        applied, budget, blocked = limit_motor_torque(cfg, requested, observation["wheels"])
        limited = bool(np.any(np.abs(requested-applied)>1e-12))
        continuous = cfg.get("actuation", {}).get("continuous_torque_nm", .04)
        continuous_over = bool(np.any(np.abs(applied)>continuous+1e-12))
        contact = plant.contact_observation()
        external = sum((np.array(d["torque_world_nm"]) for d in case.get("disturbances", [])
                        if d["start_s"]<=t+1e-9<d["start_s"]+d["duration_s"]-1e-9), start=np.zeros(3))
        row = {"time_s": t, "tilt_x_deg": float(np.rad2deg(observation["tilt"][0])),
               "tilt_y_deg": float(np.rad2deg(observation["tilt"][1])),
               "tilt_total_deg": float(np.rad2deg(observation["tilt_total"])),
               **{f"omega_{a}_deg_s": float(np.rad2deg(observation["omega"][i])) for i,a in enumerate("xyz")},
               **{f"wheel_{a}_rpm": float(observation["wheels"][i]*30/np.pi) for i,a in enumerate("xyz")},
               **{f"motor_{a}_nm": float(applied[i]) for i,a in enumerate("xyz")},
               **{f"torque_budget_{a}_nm": float(budget[i]) for i,a in enumerate("xyz")},
               **contact, "torque_limited": int(limited), "speed_governor_active": int(blocked.any()),
               "continuous_torque_exceeded": int(continuous_over), "absolute_mechanical_work_j": work,
               "measured_tilt_x_deg": float(np.rad2deg(measured[0])), "measured_tilt_y_deg": float(np.rad2deg(measured[1]))}
        rows.append(row)
        if row["tilt_total_deg"] > evaluation["loss_of_balance_deg"]:
            status = "lost_balance"
            break
        # An initial zero-force contact is allowed while the sphere loads the floor.
        if step and contact["normal_force_n"]<1e-4:
            missing_contact_s += dt
        else:
            missing_contact_s = 0.0
        excessive_slip_s = excessive_slip_s+dt if contact["slip_speed_m_s"]>slip_limit else 0.0
        if missing_contact_s >= contact_loss_hold:
            status = "lost_contact"
            break
        if excessive_slip_s >= slip_hold or contact["pivot_displacement_mm"]>max_drift:
            status = "excessive_slip"
            break
        if step==true_steps:
            break
        plant.data.xfrc_applied[:] = 0
        plant.data.xfrc_applied[plant.body, 3:] = external
        # Re-evaluate the motor envelope at the physics rate while the controller's
        # request remains held. Limiting only every control tick would allow an
        # accelerating rotor to exceed the speed-dependent physical torque budget.
        for _ in range(plant.substeps):
            actual, _, blocked = limit_motor_torque(cfg, requested, plant.data.qvel[plant.wheel_dofs])
            torque_hits += bool(np.any(np.abs(requested-actual)>1e-12))
            speed_hits += bool(blocked.any())
            continuous_hits += bool(np.any(np.abs(actual)>continuous+1e-12))
            integrated_steps += 1
            q_before = plant.data.qpos[plant.wheel_qpos].copy()
            plant.data.ctrl[:] = actual
            mujoco.mj_step(plant.model, plant.data)
            work += float(np.abs(actual*(plant.data.qpos[plant.wheel_qpos]-q_before)).sum())
        mujoco.mj_forward(plant.model, plant.data)
    intervals = max(integrated_steps, 1)
    final_window = [r for r in rows if r["time_s"]>=rows[-1]["time_s"]-1]
    summary = {
        "id": case.get("id", "contact"), "label": case.get("label", "床接触モデル"),
        "mode": "vertex_contact", "control": case.get("control", True), "status": status,
        "requested_duration_s": duration,
        "simulated_duration_s": rows[-1]["time_s"], "simulation_wall_time_s": time.perf_counter()-started,
        "initial_tilt_deg": rows[0]["tilt_total_deg"], "peak_tilt_deg": max(r["tilt_total_deg"] for r in rows),
        "final_1s_tilt_rms_deg": float(np.sqrt(np.mean([r["tilt_total_deg"]**2 for r in final_window]))),
        "final_1s_yaw_rate_rms_deg_s": float(np.sqrt(np.mean([r["omega_z_deg_s"]**2 for r in final_window]))),
        "peak_wheel_rpm": max(abs(r[f"wheel_{a}_rpm"]) for r in rows for a in "xyz"),
        "peak_motor_torque_nm": max(abs(r[f"motor_{a}_nm"]) for r in rows for a in "xyz"),
        "peak_contact_force_n": max(r["normal_force_n"] for r in rows),
        "contact_fraction": float(np.mean([r["normal_force_n"]>1e-4 for r in rows[1:]])) if len(rows)>1 else 0.0,
        "peak_slip_speed_m_s": max(r["slip_speed_m_s"] for r in rows),
        "peak_pivot_displacement_mm": max(r["pivot_displacement_mm"] for r in rows),
        "final_pivot_displacement_mm": rows[-1]["pivot_displacement_mm"],
        "torque_limited_fraction": torque_hits/intervals,
        "speed_governor_fraction": speed_hits/intervals,
        "continuous_torque_exceeded_fraction": continuous_hits/intervals,
        "absolute_mechanical_work_j": work,
        "sensor_delay_s": pipeline.delay, "seed": int(case.get("seed", cfg.get("sensing", {}).get("seed", 0))),
        "continuous_torque_limit_nm": cfg.get("actuation", {}).get("continuous_torque_nm", .04),
        "contact_corner_radius_m": cfg.get("contact", {}).get("corner_radius_m", CONTACT_DEFAULTS["corner_radius_m"]),
        "contact_sliding_friction": cfg.get("contact", {}).get("sliding_friction", CONTACT_DEFAULTS["sliding_friction"]),
        "contact_torsional_friction_m": cfg.get("contact", {}).get("torsional_friction_m", CONTACT_DEFAULTS["torsional_friction_m"]),
        "contact_rolling_friction_m": cfg.get("contact", {}).get("rolling_friction_m", CONTACT_DEFAULTS["rolling_friction_m"]),
        "note": "S2近似: 6DOF自由機体+8頂点球/床接触。対称重心のみ対応。接触・モータ・センサ特性は未実測。真の姿勢/角速度に雑音と遅延を加えた観測で、加速度計・磁気計・姿勢推定器を含むIMU物理モデルではない。エンコーダと角運動量/指令の座標変換は理想値を使用。completedは暫定停止閾値以内の完走で、実機合格ではない。電力・熱・PWM/電流制御・再生制動を予測しない。ねじり/転がり摩擦は床支点トルクを発生するので0を含む感度評価と実測が必要。",
    }
    return {"summary": summary, "rows": rows}
