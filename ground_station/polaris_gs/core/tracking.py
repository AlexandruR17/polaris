"""Cable wrap, keyhole planning and the axis motion model.

Mirrored in firmware/lib/polaris_core/tracking.cpp.
"""
import math

from . import config as C


def unwrap_near(ref, az):
    """Equivalent of az (+k*360) closest to ref."""
    return az + 360.0 * round((ref - az) / 360.0)


def unwrap_sequence(az_list):
    out = []
    prev = None
    for a in az_list:
        prev = a if prev is None else unwrap_near(prev, a)
        out.append(prev)
    return out


def plan_wrap(az_list, current_az, az_min=C.AZ_MIN_DEG, az_max=C.AZ_MAX_DEG):
    """Pick the 360 deg offset for a whole pass.

    az_list: pedestal azimuths of the pass, any branch.
    Returns (offset, ok). The unwrapped pass plus offset stays inside the
    cable limits and the first point is as close as possible to current_az.
    """
    seq = unwrap_sequence(az_list)
    lo, hi = min(seq), max(seq)
    best = None
    for k in range(-3, 4):
        off = 360.0 * k
        if lo + off < az_min - 1e-9 or hi + off > az_max + 1e-9:
            continue
        cost = abs(seq[0] + off - current_az)
        if best is None or cost < best[1] - 1e-9:
            best = (off, cost)
    if best is None:
        # pass wider than the cable range: keep the start closest
        off = unwrap_near(current_az, seq[0]) - seq[0]
        return off, False
    return best[0], True


def rate_limit_fwd_bwd(values, dt, max_rate):
    """Zero-phase rate limit: average of forward and backward limited
    profiles. Both have slope <= max_rate, so the average has too, and the
    lag is spread before and after the fast part (anticipation)."""
    n = len(values)
    if n == 0:
        return []
    step = max_rate * dt
    fwd = [values[0]] * n
    for i in range(1, n):
        d = values[i] - fwd[i - 1]
        fwd[i] = fwd[i - 1] + max(-step, min(step, d))
    bwd = [values[-1]] * n
    for i in range(n - 2, -1, -1):
        d = values[i] - bwd[i + 1]
        bwd[i] = bwd[i + 1] + max(-step, min(step, d))
    return [0.5 * (f + b) for f, b in zip(fwd, bwd)]


def max_rate(values, dt):
    m = 0.0
    for i in range(1, len(values)):
        m = max(m, abs(values[i] - values[i - 1]) / dt)
    return m


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class Axis:
    """Continuous model of AccelStepper run(): accelerate toward the target,
    decelerate when the stopping distance reaches the remaining distance.
    Positions are in steps, the reported position is an integer step count."""

    def __init__(self, max_speed_dps, accel_dps2):
        self.pos = 0.0          # steps
        self.speed = 0.0        # steps/s
        self.target = 0.0       # steps
        self.max_speed = max_speed_dps * C.STEPS_PER_DEG
        self.accel = accel_dps2 * C.STEPS_PER_DEG
        self.enabled = True

    def set_limits(self, max_speed_dps, accel_dps2):
        self.max_speed = max_speed_dps * C.STEPS_PER_DEG
        self.accel = accel_dps2 * C.STEPS_PER_DEG

    def move_to(self, steps):
        self.target = float(round(steps))

    def stop_now(self):
        self.speed = 0.0
        self.target = self.position

    def set_position(self, steps):
        self.pos = float(steps)
        self.target = float(steps)
        self.speed = 0.0

    @property
    def position(self):
        return float(round(self.pos))

    @property
    def deg(self):
        return self.position / C.STEPS_PER_DEG

    def run(self, dt):
        if not self.enabled:
            self.speed = 0.0
            return
        dist = self.target - self.pos
        if abs(dist) < 0.5 and abs(self.speed) < self.accel * dt * 2:
            self.pos = self.target
            self.speed = 0.0
            return
        stop_dist = self.speed * self.speed / (2.0 * self.accel)
        moving_away = self.speed * dist < 0
        if moving_away or abs(dist) <= stop_dist:
            dv = self.accel * dt
            if abs(self.speed) <= dv:
                self.speed = 0.0
            else:
                self.speed -= math.copysign(dv, self.speed)
            if not moving_away and self.speed == 0.0:
                self.speed = math.copysign(min(self.accel * dt, self.max_speed), dist)
        else:
            self.speed += math.copysign(self.accel * dt, dist)
            self.speed = clamp(self.speed, -self.max_speed, self.max_speed)
        new = self.pos + self.speed * dt
        # do not overshoot the target while approaching it
        if (self.target - self.pos) * (self.target - new) < 0 and not moving_away:
            new = self.target
            self.speed = 0.0
        self.pos = new
