"""Axis position controller: two-degree-of-freedom PID with velocity output.
Mirror of firmware/lib/polaris_core/pc_control.h (same operations, same order).

    e  = r - y                                  tracking error, axis frame [deg]
    ff = Kff * r'       r' low-pass filtered (tau_r)        feed-forward [deg/s]
    P  = Kp * e
    D  = -Kd * y'       on the measurement, low-pass (tau_d): no kick when r jumps
    v  = ff + P + I + D                         unsaturated command [deg/s]
    u  = sat(v): |u| <= vmax, |u - u_prev| <= amax * dt     actuator limits
    I += Ki * e * dt + Kt * (u - v) * dt        back-calculation anti-windup

The plant seen by this loop is the stepper axis in speed mode: an integrator
(y' = u) with an acceleration limit. Backward Euler, sample time = control period.
"""
from dataclasses import dataclass, field


@dataclass
class Gains:
    kp: float = 0.0     # 1/s
    ki: float = 0.0     # 1/s^2
    kd: float = 0.0     # s
    kff: float = 1.0    # feed-forward weight (0 or 1)


@dataclass
class Terms:
    e: float = 0.0
    ff: float = 0.0
    p: float = 0.0
    i: float = 0.0
    d: float = 0.0
    u: float = 0.0


@dataclass
class AxisPid:
    gains: Gains = field(default_factory=Gains)
    vmax: float = 1.0
    amax: float = 1.0
    tau_r: float = 0.1
    tau_d: float = 0.05
    kt: float = 1.0
    terms: Terms = field(default_factory=Terms)
    r_prev: float = 0.0
    y_prev: float = 0.0
    r_dot: float = 0.0

    def reset(self, r, y):
        """Bumpless start: no integral, no rate history, actuator at rest."""
        self.r_prev, self.y_prev, self.r_dot = r, y, 0.0
        self.terms = Terms()
        self.terms.e = r - y

    def update(self, r, y, dt):
        t, g = self.terms, self.gains
        t.e = r - y
        self.r_dot += dt / (self.tau_r + dt) * ((r - self.r_prev) / dt - self.r_dot)
        t.d += dt / (self.tau_d + dt) * (-g.kd * (y - self.y_prev) / dt - t.d)
        self.r_prev, self.y_prev = r, y
        t.ff = g.kff * self.r_dot
        t.p = g.kp * t.e
        v = t.ff + t.p + t.i + t.d
        u = v
        if u > self.vmax:
            u = self.vmax
        if u < -self.vmax:
            u = -self.vmax
        du = self.amax * dt
        if u > t.u + du:
            u = t.u + du
        if u < t.u - du:
            u = t.u - du
        t.i += g.ki * t.e * dt + self.kt * (u - v) * dt
        t.u = u
        return u
