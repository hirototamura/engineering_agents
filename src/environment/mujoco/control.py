import mujoco
import numpy as np
from scipy.linalg import solve_discrete_are

from .model import Plant


class Regulator:
    """Discrete LQR on tilt, tilt rates and transverse wheel momentum; yaw-rate damper."""
    def __init__(self, cfg, mode):
        plant = Plant(cfg, mode)
        n, inputs = (3, 1) if mode == "edge" else (6, 2)
        self.a, self.b = np.zeros((n, n)), np.zeros((n, inputs))

        def transition(x, u):
            plant.set_state(x)
            torque = u if mode == "edge" else np.r_[u, 0]
            plant.advance(plant.motor_command(torque), speed_limit=False)
            return plant.observe()["state"]

        for i in range(n):
            e = np.eye(n)[i] * (1e-6 if i >= n-inputs else 1e-5)
            self.a[:, i] = (transition(e, np.zeros(inputs)) - transition(-e, np.zeros(inputs))) / (2*e[i])
        for i in range(inputs):
            e = np.eye(inputs)[i]*1e-5
            self.b[:, i] = (transition(np.zeros(n), e) - transition(np.zeros(n), -e))/(2*e[i])
        q = np.diag(cfg["controller"][f"{mode}_q"])
        r = np.diag(cfg["controller"][f"{mode}_r"])
        p = solve_discrete_are(self.a, self.b, q, r)
        self.k = np.linalg.solve(r + self.b.T@p@self.b, self.b.T@p@self.a)
        self.eigenvalues = np.linalg.eigvals(self.a-self.b@self.k)
        self.mode, self.yaw_gain = mode, cfg["controller"]["yaw_rate_gain_nm_s"]

    def command(self, plant):
        obs = plant.observe()
        torque = -self.k @ obs["state"]
        if self.mode == "vertex":
            torque = np.r_[torque, self.yaw_gain*obs["omega"][2]]
        return plant.motor_command(torque)

    def as_dict(self):
        return {"state_order": ["theta", "omega", "wheel_momentum"] if self.mode == "edge" else ["tilt_x", "tilt_y", "omega_x", "omega_y", "wheel_momentum_x", "wheel_momentum_y"], "K": self.k.tolist(), "closed_loop_eigenvalue_abs": np.abs(self.eigenvalues).tolist(), "yaw_rate_gain_nm_s": self.yaw_gain, "note": "Finite-difference linearization of MuJoCo at equilibrium; fixed SI gains across cases."}
