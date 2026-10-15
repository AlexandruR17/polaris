"""Vehicle motion generator: what the laptop sends as VEH:<roll>,<pitch>,<yaw>.

Angles in degrees, ROS REP-103 (yaw 90 = facing north). Deterministic for a
given seed, so experiments are repeatable.
"""
import math
import random

MODES = {
    "stationary": "Staționar",
    "bumpy": "Drum denivelat",
    "turn": "Viraj",
    "slope": "Pantă",
}


class VehicleMotion:
    def __init__(self, mode="stationary", yaw0=90.0, seed=1):
        self.mode = mode
        self.yaw0 = yaw0
        self.rng = random.Random(seed)
        self._noise_r = 0.0
        self._noise_p = 0.0

    def set_mode(self, mode):
        self.mode = mode

    def attitude(self, t):
        """(roll, pitch, yaw) at time t (seconds since start)."""
        m = self.mode
        if m == "bumpy":
            # body roll and pitch from road bumps: a few tones plus filtered noise
            self._noise_r = 0.9 * self._noise_r + 0.1 * self.rng.gauss(0, 1.2)
            self._noise_p = 0.9 * self._noise_p + 0.1 * self.rng.gauss(0, 1.0)
            roll = 3.0 * math.sin(2 * math.pi * 0.7 * t) + 1.5 * math.sin(2 * math.pi * 1.9 * t + 1.0)
            pitch = 2.5 * math.sin(2 * math.pi * 0.5 * t + 0.5) + 1.2 * math.sin(2 * math.pi * 2.3 * t)
            yaw = self.yaw0 + 2.0 * math.sin(2 * math.pi * 0.05 * t)
            return roll + self._noise_r, pitch + self._noise_p, yaw
        if m == "turn":
            # steady turn at 6 deg/s with body lean
            ramp = min(1.0, t / 3.0)
            return 4.0 * ramp, 0.5 * ramp, (self.yaw0 + 6.0 * t) % 360.0
        if m == "slope":
            ramp = min(1.0, t / 4.0)
            return 2.0 * ramp, -8.0 * ramp, self.yaw0
        return 0.0, 0.0, self.yaw0
