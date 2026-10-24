from __future__ import annotations

import copy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]


def config(path=None):
    return json.loads(Path(path or ROOT / "config/reference.json").read_text())


def fmt(values):
    return " ".join(f"{x:.12g}" for x in np.atleast_1d(values))


def quat(rotation):
    x, y, z, w = Rotation.from_matrix(rotation).as_quat()
    return np.array([w, x, y, z])


def equilibrium_rotation(mode):
    if mode == "edge":
        return Rotation.from_euler("x", 45, degrees=True).as_matrix()
    return np.array([[1, -1, 0], [1, 1, -2], [1, 1, 1]]) / np.array([[2**0.5], [6**0.5], [3**0.5]])


def wheel_centers_body_m(cfg):
    """Fixed mounting faces in body coordinates; not adaptive to the active corner.

    The first trial supports corner 000. Its three incident faces have x=0,
    y=0 and z=0. Missing metadata preserves the historical opposite-face model.
    Rotor positive-axis conventions do not change when the mount moves.
    """
    p = cfg["physics"]
    side, inset = p["cube_side_m"], p["wheel_face_inset_m"]
    mount = p.get("wheel_mount_side", "far_corner_000")
    if mount not in {"near_corner_000", "far_corner_000"}:
        raise ValueError("wheel_mount_side must be near_corner_000 or far_corner_000")
    if not np.isfinite(inset) or not 0 < inset < side / 2:
        raise ValueError("wheel_face_inset_m must be between zero and side/2")
    centers = np.full((3, 3), side / 2)
    np.fill_diagonal(centers, inset if mount == "near_corner_000" else side - inset)
    return centers


def build_xml(cfg, mode="vertex", free=False):
    """Geometries are visual only. Pivot joints, inertias and motor torques drive physics."""
    p = cfg["physics"]
    s, b = p["cube_side_m"], p["cube_side_m"] / 2
    root = ET.Element("mujoco", model=f"reaction_wheel_cube_{mode}")
    ET.SubElement(root, "compiler", angle="radian", autolimits="true")
    ET.SubElement(root, "option", timestep=str(p["timestep_s"]), gravity=f"0 0 {-p['gravity_m_s2']}", integrator="RK4")
    ET.SubElement(root, "size", njmax="200", nconmax="100")
    visual = ET.SubElement(root, "visual")
    ET.SubElement(visual, "global", offwidth="1280", offheight="960")
    ET.SubElement(visual, "quality", shadowsize="2048")
    ET.SubElement(visual, "headlight", ambient=".4 .4 .4", diffuse=".7 .7 .7", specular=".15 .15 .15")
    default = ET.SubElement(root, "default")
    ET.SubElement(default, "geom", contype="0", conaffinity="0", mass="0")
    ET.SubElement(default, "joint", damping=str(p["joint_damping_nm_s"]))
    asset = ET.SubElement(root, "asset")
    ET.SubElement(asset, "texture", name="floor", type="2d", builtin="checker", rgb1=".09 .13 .18", rgb2=".12 .17 .23", width="512", height="512")
    ET.SubElement(asset, "material", name="floor", texture="floor", texrepeat="8 8", reflectance=".08")
    world = ET.SubElement(root, "worldbody")
    ET.SubElement(world, "light", pos=".5 -.4 1.5", dir="-.3 .2 -1", directional="true")
    ET.SubElement(world, "geom", name="visual_floor", type="plane", size="1.5 1.5 .01", material="floor")
    ET.SubElement(world, "geom", name="ideal_pivot", type="sphere", pos="0 0 .01", size=".008", rgba=".12 .9 .72 1")
    r0 = equilibrium_rotation(mode)
    body = ET.SubElement(world, "body", name="cube", pos=fmt([-b if mode == "edge" else 0, 0, .01]), quat=fmt(quat(r0)))
    if free:
        ET.SubElement(body, "freejoint", name="pivot")
    elif mode == "edge":
        ET.SubElement(body, "joint", name="pivot", type="hinge", axis="1 0 0")
    else:
        ET.SubElement(body, "joint", name="pivot", type="ball")
    ET.SubElement(body, "inertial", pos=fmt(s * np.array(p["frame_com_fraction"])), mass=str(p["frame_mass_kg"]), diaginertia=fmt(p["frame_inertia_kg_m2"]))
    # Twelve beams. Mass is declared once in the inertial, not by the decorative geometry.
    for axis in range(3):
        other = [a for a in range(3) if a != axis]
        for a in (0, s):
            for c in (0, s):
                start, end = np.zeros(3), np.zeros(3)
                start[other] = end[other] = [a, c]
                end[axis] = s
                ET.SubElement(body, "geom", type="capsule", fromto=fmt([*start, *end]), size=".004", rgba=".83 .9 .96 1")
    ET.SubElement(body, "geom", name="electronics", type="box", pos=fmt([b, b, b]), size=fmt([s*.16, s*.12, s*.07]), rgba=".12 .3 .28 1")
    ET.SubElement(body, "geom", type="box", pos=fmt([b, b, b-s*.1]), size=fmt([s*.11, s*.07, s*.05]), rgba=".24 .27 .36 1")
    ET.SubElement(body, "site", name="imu", pos=fmt([b, b, b]), size=".003", rgba="1 .85 .2 1")
    colors = ["1 .46 .19 1", ".22 .66 1 1", ".69 .45 1 1"]
    for i, (axis, pos) in enumerate(zip(np.eye(3), wheel_centers_body_m(cfg))):
        rw = Rotation.align_vectors([axis], [[0, 0, 1]])[0].as_matrix()
        wheel = ET.SubElement(body, "body", name=f"wheel_{i}", pos=fmt(pos), quat=fmt(quat(rw)))
        ET.SubElement(wheel, "joint", name=f"rotor_{i}", type="hinge", axis="0 0 1")
        ET.SubElement(wheel, "inertial", pos="0 0 0", mass=str(p["wheel_mass_kg"]), diaginertia=fmt([p["wheel_transverse_inertia_kg_m2"]]*2+[p["wheel_axial_inertia_kg_m2"]]))
        radius, thickness = p["wheel_radius_m"], p["wheel_thickness_m"]
        # Ring with a gap-free set of segments plus spokes visibly rotating with the joint.
        for k in range(32):
            a, c = 2*np.pi*k/32, 2*np.pi*(k+1)/32
            ET.SubElement(wheel, "geom", type="capsule", fromto=fmt([radius*np.cos(a), radius*np.sin(a), 0, radius*np.cos(c), radius*np.sin(c), 0]), size=str(thickness/2), rgba=colors[i])
        ET.SubElement(wheel, "geom", type="cylinder", size=fmt([radius*.19, thickness*.7]), rgba=".18 .22 .29 1")
        for k in range(3):
            a = 2*np.pi*k/3
            ET.SubElement(wheel, "geom", type="capsule", fromto=fmt([0, 0, 0, radius*np.cos(a), radius*np.sin(a), 0]), size=".0025", rgba=colors[i])
        ET.SubElement(wheel, "geom", type="sphere", pos=fmt([radius*.9, 0, thickness]), size=".005", rgba="1 1 1 1")
    actuators = ET.SubElement(root, "actuator")
    for i in range(3):
        lim = p["motor_torque_limit_nm"]
        ET.SubElement(actuators, "motor", name=f"motor_{i}", joint=f"rotor_{i}", gear="1", ctrllimited="true", ctrlrange=fmt([-lim, lim]))
    return ET.tostring(root, encoding="unicode")


class Plant:
    def __init__(self, cfg, mode="vertex", free=False):
        self.cfg = copy.deepcopy(cfg)
        self.mode = mode
        self.xml = build_xml(cfg, mode, free)
        self.model = mujoco.MjModel.from_xml_string(self.xml)
        self.data = mujoco.MjData(self.model)
        self.body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "cube")
        ids = [mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, f"rotor_{i}") for i in range(3)]
        self.wheel_dofs = self.model.jnt_dofadr[ids]
        self.wheel_qpos = self.model.jnt_qposadr[ids]
        self.r0 = equilibrium_rotation(mode)
        self.wheel_j = cfg["physics"]["wheel_axial_inertia_kg_m2"]
        n = cfg["physics"]["control_period_s"] / cfg["physics"]["timestep_s"]
        if not np.isclose(n, round(n)):
            raise ValueError("control_period_s must be an integer multiple of timestep_s")
        self.substeps = round(n)
        mujoco.mj_forward(self.model, self.data)

    @property
    def rotation(self):
        return self.data.xmat[self.body].reshape(3, 3)

    def observe(self):
        velocity = np.zeros(6)
        mujoco.mj_objectVelocity(self.model, self.data, mujoco.mjtObj.mjOBJ_BODY, self.body, velocity, 0)
        direction = self.rotation @ (np.ones(3)/np.sqrt(3))
        tilt = np.array([np.arctan2(-direction[1], direction[2]), np.arctan2(direction[0], direction[2])])
        wheels = self.data.qvel[self.wheel_dofs].copy()
        h = self.rotation @ (self.wheel_j*wheels)
        if self.mode == "edge":
            state = np.array([self.data.qpos[0], velocity[0], self.wheel_j*wheels[0]])
            angle = abs(self.data.qpos[0])
        else:
            state = np.r_[tilt, velocity[:2], h[:2]]
            angle = np.arccos(np.clip(direction[2], -1, 1))
        return {"state": state, "tilt": tilt, "tilt_total": angle, "omega": velocity[:3], "wheels": wheels, "momentum": h}

    def set_state(self, state=None, tilt_deg=None, yaw_rate=0):
        mujoco.mj_resetData(self.model, self.data)
        if state is None:
            theta = np.deg2rad(tilt_deg or [0, 0])
            state = np.r_[theta[0], 0, 0] if self.mode == "edge" else np.r_[theta, 0, 0, 0, 0]
        if self.mode == "edge":
            self.data.qpos[0] = state[0]
            self.data.qvel[0] = state[1]
            self.data.qvel[self.wheel_dofs[0]] = state[2]/self.wheel_j
        else:
            delta_world = Rotation.from_rotvec([state[0], state[1], 0]).as_matrix()
            self.data.qpos[:4] = quat(self.r0.T @ delta_world @ self.r0)
            r = delta_world @ self.r0
            self.data.qvel[:3] = r.T @ np.array([state[2], state[3], yaw_rate])
            self.data.qvel[self.wheel_dofs] = r.T @ np.array([state[4], state[5], 0]) / self.wheel_j
        mujoco.mj_forward(self.model, self.data)

    def motor_command(self, world_or_edge):
        if self.mode == "edge":
            return np.array([float(np.asarray(world_or_edge).ravel()[0]), 0, 0])
        return self.rotation.T @ np.asarray(world_or_edge)

    def advance(self, motors, disturbance=None, speed_limit=True):
        limit = self.cfg["physics"]["motor_torque_limit_nm"]
        applied = np.clip(motors, -limit, limit)
        if speed_limit:
            rates = self.data.qvel[self.wheel_dofs]
            blocked = (abs(rates) >= self.cfg["physics"]["wheel_speed_limit_rad_s"]) & (np.sign(applied) == np.sign(rates))
            applied[blocked] = 0
        self.data.ctrl[:] = applied
        self.data.xfrc_applied[:] = 0
        if disturbance is not None:
            self.data.xfrc_applied[self.body, 3:] = disturbance
        mujoco.mj_step(self.model, self.data, nstep=self.substeps)
        mujoco.mj_forward(self.model, self.data)
        return applied

