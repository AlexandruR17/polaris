"""Runs the Python controller with modelled axes.

Same loop as firmware/test_native/harness.cpp (scenario mode) and the same
order of operations as main.cpp: inputs -> controller.update -> apply
outputs -> axes move for one control period.
"""
from ..core import config as C
from ..core.tle_data import FALLBACK_TLE
from ..core.tracking import Axis
from .controller import Controller, Inputs

DT_MS = 1000 // C.CONTROL_HZ


class SimRig:
    """Controller + two modelled axes + operator inputs."""

    def __init__(self, emit, t0, sim_limits=True, tles=None):
        self.ctl = Controller()
        self.ctl.begin(sim_limits, emit)
        for catnr, (name, l1, l2) in (tles or FALLBACK_TLE).items():
            self.ctl.load_tle(catnr, name, l1, l2, True, t0, False)
        self.az = Axis(C.AZ_MAX_SPEED_DPS, C.AZ_ACCEL_DPS2)
        self.el = Axis(C.EL_MAX_SPEED_DPS, C.EL_ACCEL_DPS2)
        self.inp = Inputs()

    def step(self, ms, t_real):
        """One control period. Edge inputs (buttons, encoder) are cleared after."""
        inp = self.inp
        inp.ms = ms
        inp.t_real = t_real
        inp.az_steps = int(self.az.position)
        inp.el_steps = int(self.el.position)
        o = self.ctl.update(inp)
        self.apply(o)
        for _ in range(DT_MS):
            self.az.run(0.001)
            self.el.run(0.001)
        inp.btn_home = inp.btn_mode = inp.btn_stow = inp.encoder_press = False
        inp.encoder_delta = 0
        return o

    def apply(self, o):
        self.az.enabled = self.el.enabled = o.drivers_enabled
        if o.stop_now:
            self.az.stop_now()
            self.el.stop_now()
        if o.az.max_speed_dps > 0:
            self.az.set_limits(o.az.max_speed_dps, o.az.accel_dps2)
        if o.el.max_speed_dps > 0:
            self.el.set_limits(o.el.max_speed_dps, o.el.accel_dps2)
        if o.az.set_pos:
            self.az.set_position(o.az.target)
        else:
            self.az.move_to(o.az.target)
        if o.el.set_pos:
            self.el.set_position(o.el.target)
        else:
            self.el.move_to(o.el.target)


def parse_scenario(text):
    t0, end, steps, sim_limits = 1792015503.0, 60000, [], True
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("T0 "):
            t0 = float(line[3:])
        elif line.startswith("SIMLIMITS "):
            sim_limits = line[10:].strip() != "0"
        elif line.startswith("END "):
            end = int(line[4:])
        elif line.startswith("@"):
            parts = line[1:].split(None, 2)
            ms, op = int(parts[0]), parts[1]
            arg = parts[2] if len(parts) > 2 else ""
            steps.append((ms, op, arg))
    return t0, end, steps, sim_limits


def run_scenario(text):
    """Return the emitted lines as 'ms line', like the C++ harness."""
    t0, end, steps, sim_limits = parse_scenario(text)
    out = []
    state = {"ms": 0}
    rig = SimRig(lambda line: out.append(f"{state['ms']} {line}"), t0, sim_limits)
    inp = rig.inp
    k = 0
    for ms in range(0, end + 1, DT_MS):
        state["ms"] = ms
        inp.ms = ms
        inp.t_real = t0 + ms / 1000.0
        while k < len(steps) and steps[k][0] <= ms:
            _, op, arg = steps[k]
            k += 1
            if op == "BOOT":
                rig.ctl.boot_done(inp)
            elif op == "CMD":
                rig.ctl.command(arg)
            elif op == "ESTOP":
                inp.estop = arg.strip() != "0"
            elif op == "LIMAZ":
                inp.lim_az = arg.strip() != "0"
            elif op == "LIMEL":
                inp.lim_el = arg.strip() != "0"
            elif op == "BTN":
                a = arg.strip()
                inp.btn_home |= a == "HOME"
                inp.btn_mode |= a == "MODE"
                inp.btn_stow |= a == "STOW"
                inp.encoder_press |= a == "ENC"
            elif op == "ENC":
                inp.encoder_delta = int(arg)
            elif op == "POT":
                inp.pot_frac = float(arg)
            elif op == "TLEFAIL":
                rig.ctl.tle_download_failed(int(arg), inp.t_real)
            elif op == "IMU":
                if arg.strip() == "OFF":
                    inp.imu_ok = False
                else:
                    inp.imu_ok = True
                    inp.ax, inp.ay, inp.az, inp.gx, inp.gy = (float(x) for x in arg.split())
        rig.step(ms, t0 + ms / 1000.0)
    return out
