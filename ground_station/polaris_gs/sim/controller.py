"""Python copy of the firmware state machine (pc_controller.cpp).

Same states, same events, same telemetry text. The dashboard uses it when no
ESP32 is connected; tests run it side by side with the native C++ build.
"""
import math
from dataclasses import dataclass

from ..core import config as C
from ..core import geometry as G
from ..core import protocol as P
from ..core import tracking as T
from ..core.orbit import Satellite

STATES = P.STATES
MODES = ("AUTO", "MANUAL", "DEMO", "IDLE", "STOW")
SAT_IDS = (25544, 33591, 28654, 43700)

BEEP_NONE, BEEP_AOS, BEEP_LOS, BEEP_ERROR, BEEP_OK = range(5)
LED_GREEN, LED_YELLOW, LED_RED = 1, 2, 4


def nearbyint(x):
    return float(round(x))  # Python round is half to even, like nearbyint


def to_steps(deg):
    return int(round(deg * C.STEPS_PER_DEG))


@dataclass
class Inputs:
    ms: int = 0
    t_real: float = 0.0
    estop: bool = False
    lim_az: bool = False
    lim_el: bool = False
    az_steps: int = 0
    el_steps: int = 0
    imu_ok: bool = False
    ax: float = 0.0
    ay: float = 0.0
    az: float = 1.0
    gx: float = 0.0
    gy: float = 0.0
    encoder_delta: int = 0
    encoder_press: bool = False
    btn_mode: bool = False
    btn_home: bool = False
    btn_stow: bool = False
    pot_frac: float = 0.5


@dataclass
class AxisCmd:
    target: int = 0
    set_pos: bool = False
    max_speed_dps: float = 0.0
    accel_dps2: float = 0.0


@dataclass
class Outputs:
    drivers_enabled: bool = False
    relay_on: bool = False
    stop_now: bool = False
    az: AxisCmd = None
    el: AxisCmd = None
    leds: int = 0
    beep: int = BEEP_NONE
    tle_request: int = 0

    def __post_init__(self):
        self.az = AxisCmd()
        self.el = AxisCmd()


class ComplementaryFilter:
    def __init__(self, alpha):
        self.alpha = alpha
        self.init = False
        self.roll = 0.0
        self.pitch = 0.0

    def update(self, ax, ay, az, gx, gy, dt):
        r_acc, p_acc = G.accel_to_roll_pitch(ax, ay, az)
        if not self.init or dt <= 0 or dt > 0.5:
            self.roll, self.pitch, self.init = r_acc, p_acc, True
            return
        a = self.alpha
        self.roll = a * (self.roll + gx * dt) + (1.0 - a) * r_acc
        self.pitch = a * (self.pitch + gy * dt) + (1.0 - a) * p_acc


class _Pass:
    def __init__(self, p=None):
        self.valid = p is not None
        self.aos = p.aos if p else 0.0
        self.sets = bool(p and p.los is not None)
        self.los = p.los if (p and p.los is not None) else 0.0
        self.tmax = p.tmax if p else 0.0
        self.max_el = p.max_el if p else 0.0
        self.aos_az = p.aos_az if p else 0.0


def _fmt_iso_or_null(t, valid):
    return f'"{P.iso_utc(t)}"' if valid else "null"


class Controller:
    def __init__(self):
        self.sim_limits = True
        self.emit_fn = None
        self.slots = {i: {"loaded": False, "fallback": False, "tried": False, "name": "",
                          "l1": "", "l2": ""} for i in SAT_IDS}
        self.sat = None
        self.sat_id = C.DEFAULT_SAT
        self.state = "BOOT"
        self.mode = "AUTO"
        self.out = Outputs()
        self.tick = 0
        self.ms = 0
        self.inp = Inputs()
        # clock
        self.t_sim = 0.0
        self.demo = False
        self.warp = 1
        self.demo_warp = C.DEFAULT_DEMO_WARP
        self.anchor_ms = 0
        self.anchor_sim = 0.0
        # attitude
        self.filter = ComplementaryFilter(C.COMP_FILTER_ALPHA)
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = C.VEHICLE_YAW_DEFAULT_DEG
        self.veh_active = False
        self.veh = (0.0, 0.0, 0.0)
        self.veh_ms = 0
        self.imu_ms = 0
        self.imu_seen = False
        self.src = "NONE"
        self.comp = True
        self.planner = True  # experiment switch, not in the firmware
        # look
        self.look = None
        self.look_t = 0.0
        self.prev_enu = (0.0, 0.0, 1.0)
        self.prev_t = 0.0
        self.prev_valid = False
        # pass and plan
        self.pass_ = _Pass()
        self.pass_try_ms = 0
        self.pass_tried = False
        self.plan_valid = False
        self.plan_n = 0
        self.plan_t0 = 0.0
        self.plan_dt = 1.0
        self.plan_start_az = 0.0
        self.plan_start_el = 0.0
        self.plan_lead = []
        self.plan_az = []
        # pointing
        self.ant_az = 0.0
        self.ant_el = 0.0
        self.cmd_az = 0.0
        self.cmd_el = 0.0
        self.have_raw = False
        self.raw_az = 0.0
        self.raw_ms = 0
        self.req_rate = 0.0
        self.err = 0.0
        self.keyhole = False
        self.kh_zenith = False
        self.kh_ms = 0
        self.err_sum2 = 0.0
        self.err_max = 0.0
        self.err_n = 0
        # homing
        self.home_start_ms = 0
        self.az_homed = False
        self.el_homed = False
        self.az_start = 0
        self.el_start = 0
        self.lim_armed_az = True
        self.lim_armed_el = True
        # manual
        self.man_axis_el = False
        self.man_az = 0.0
        self.man_el = 0.0
        # safety
        self.estop_released_said = False
        self.fault = ""
        self.pending_tle = 0
        self.pending_beep = BEEP_NONE

    # ------------------------------------------------------------ output
    def emit(self, line):
        if self.emit_fn:
            self.emit_fn(line)

    def begin(self, sim_limits, emit_fn):
        self.sim_limits = sim_limits
        self.emit_fn = emit_fn
        self.state = "BOOT"
        self.emit('{"ev":"BOOT","fw":"%s","sim":%d}' % (C.FW_VERSION, 1 if sim_limits else 0))

    def set_state(self, s):
        if s == self.state:
            return
        self.emit('{"ev":"MODE","from":"%s","to":"%s"}' % (self.state, s))
        self.state = s

    # ------------------------------------------------------------ TLE
    def tle_fallback(self):
        s = self.slots.get(self.sat_id)
        return s is None or s["fallback"]

    def load_tle(self, catnr, name, l1, l2, fallback, t_now, announce):
        if catnr not in self.slots:
            return False
        try:
            probe = Satellite(name, l1, l2)
        except Exception:
            self.emit('{"ev":"ERR","msg":"BAD_TLE","sat":%d}' % catnr)
            return False
        s = self.slots[catnr]
        s.update(name=name[:24], l1=l1, l2=l2, loaded=True, fallback=fallback)
        if not fallback:
            s["tried"] = True
        if announce:
            self.emit('{"ev":"%s","sat":%d,"age_d":%.1f}' % ("TLE_FALLBACK" if fallback else "TLE_OK",
                                                           catnr, probe.age_days(t_now)))
        if catnr == self.sat_id:
            self.sat = Satellite(s["name"], s["l1"], s["l2"])
            self.pass_ = _Pass()
            self.pass_tried = False
            self.plan_valid = False
            self.refresh_look(True)
        return True

    def tle_download_failed(self, catnr, t_now):
        s = self.slots.get(catnr)
        if s is None or not s["loaded"]:
            return
        s["tried"] = True
        probe = Satellite(s["name"], s["l1"], s["l2"])
        self.emit('{"ev":"TLE_FALLBACK","sat":%d,"age_d":%.1f}' % (catnr, probe.age_days(t_now)))

    def select_sat(self, sid):
        self.sat_id = sid
        s = self.slots[sid]
        if s["loaded"]:
            self.sat = Satellite(s["name"], s["l1"], s["l2"])
        if s["fallback"] and not s["tried"]:
            self.pending_tle = sid
            s["tried"] = True
        self.pass_ = _Pass()
        self.pass_tried = False
        self.plan_valid = False
        self.refresh_look(True)
        if self.demo:
            self.end_demo()
        if self.state in ("ACQUIRE", "TRACK", "WAIT_AOS", "DEMO"):
            self.mode = "AUTO"
            self.enter_wait_aos()

    # ------------------------------------------------------------ look
    def refresh_look(self, reset):
        if reset:
            self.prev_valid = False
        if self.sat is None:
            self.look = None
            return
        try:
            lk = self.sat.look(self.t_sim)
        except RuntimeError:
            self.look = None
            return
        enu = (math.cos(math.radians(lk.el)) * math.sin(math.radians(lk.az)),
               math.cos(math.radians(lk.el)) * math.cos(math.radians(lk.az)),
               math.sin(math.radians(lk.el)))
        lk.enu = enu
        if self.look is not None and not reset:
            self.prev_enu = self.look.enu
            self.prev_t = self.look_t
            self.prev_valid = self.t_sim > self.look_t
        self.look = lk
        self.look_t = self.t_sim

    def sat_enu_at(self, t):
        v = self.look.enu
        if self.prev_valid and self.look_t > self.prev_t:
            k = (t - self.look_t) / (self.look_t - self.prev_t)
            k = min(max(k, 0.0), 2.0)
            p = self.prev_enu
            v = (v[0] + (v[0] - p[0]) * k, v[1] + (v[1] - p[1]) * k, v[2] + (v[2] - p[2]) * k)
            n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
            v = (v[0] / n, v[1] / n, v[2] / n)
        return v

    # ------------------------------------------------------------ planning
    def compute_pass(self, t):
        p = self.sat.next_pass(t, C.PASS_SEARCH_H, C.MASK_EL_DEG)
        self.pass_ = _Pass(p)
        self.pass_tried = True
        self.pass_try_ms = self.ms
        self.plan_valid = False
        if not self.pass_.valid:
            self.emit('{"ev":"INFO","msg":"NO_PASS","sat":%d}' % self.sat_id)
            return
        ps = self.pass_
        self.emit('{"ev":"PASS","sat":%d,"aos":"%s","los":%s,"max_el":%.1f,"aos_az":%.1f}'
                  % (self.sat_id, P.iso_utc(ps.aos), _fmt_iso_or_null(ps.los, ps.sets), ps.max_el,
                     ps.aos_az))
        self.build_plan(t, self.ant_az)

    def build_plan(self, t_from, ref_az):
        self.plan_valid = False
        ps = self.pass_
        if not ps.valid or not ps.sets:
            return
        t0 = ps.aos if ps.aos > t_from else t_from
        dur = ps.los - t0
        if dur <= 0:
            return
        n = int(dur / C.PASS_SAMPLE_S) + 1
        n = min(n, C.PASS_MAX_SAMPLES)
        n = max(n, 2)
        dt = dur / (n - 1)
        seq = []
        el0 = 0.0
        for i in range(n):
            lk = self.sat.look(t0 + i * dt)
            a, e = G.pointing_command(lk.az, lk.el, self.roll, self.pitch, self.yaw, self.comp)
            seq.append(a)
            if i == 0:
                el0 = e
        seq = T.unwrap_sequence(seq)
        off, ok = T.plan_wrap(seq, ref_az)
        seq = [a + off for a in seq]
        if not ok:
            self.emit('{"ev":"INFO","msg":"WRAP_UNAVOIDABLE"}')
        w = float(self.warp if self.demo else 1)
        vmax = C.KEYHOLE_PLAN_MARGIN * C.AZ_MAX_SPEED_DPS / w
        req = T.max_rate(seq, dt)
        prof = T.rate_limit_fwd_bwd(seq, dt, vmax)
        self.plan_az = seq
        # planner off (experiments only, the firmware always plans): no anticipation
        self.plan_lead = [p - s for p, s in zip(prof, seq)] if self.planner else [0.0] * n
        self.plan_n = n
        self.plan_t0 = t0
        self.plan_dt = dt
        self.plan_start_az = prof[0]
        self.plan_start_el = T.clamp(el0, C.EL_MIN_DEG, C.EL_MAX_DEG)
        self.plan_valid = True
        if req > vmax:
            self.emit('{"ev":"KEYHOLE","pred":1,"req_dps":%.1f,"max_dps":%.1f}'
                      % (req * w, C.AZ_MAX_SPEED_DPS))

    def _interp(self, tab, t):
        x = (t - self.plan_t0) / self.plan_dt
        if x <= 0:
            return tab[0]
        if x >= self.plan_n - 1:
            return tab[self.plan_n - 1]
        i = int(x)
        f = x - i
        return tab[i] + (tab[i + 1] - tab[i]) * f

    def plan_lead_at(self, t):
        return self._interp(self.plan_lead, t) if self.plan_valid else 0.0

    def plan_az_at(self, t):
        return self._interp(self.plan_az, t)

    # ------------------------------------------------------------ entries
    def boot_done(self, inp):
        self.inp = inp
        self.ms = inp.ms
        self.t_sim = inp.t_real
        if self.state != "BOOT":
            return
        if self.sat is None:
            self.select_sat(self.sat_id)
        self.start_homing()

    def start_homing(self):
        if self.demo:
            self.end_demo()
        self.set_state("HOMING")
        self.home_start_ms = self.ms
        self.az_homed = self.el_homed = False
        self.az_start = self.inp.az_steps
        self.el_start = self.inp.el_steps
        self.out.drivers_enabled = True
        self.out.relay_on = True
        self.set_targets(self.inp.az_steps / C.STEPS_PER_DEG - 720.0,
                         self.inp.el_steps / C.STEPS_PER_DEG - 200.0,
                         C.HOMING_SPEED_DPS, C.AZ_ACCEL_DPS2, C.HOMING_SPEED_DPS, C.EL_ACCEL_DPS2)

    def after_homing(self):
        self.emit('{"ev":"HOME_OK","t_s":%.1f}' % ((self.ms - self.home_start_ms) / 1000.0))
        self.pending_beep = BEEP_OK
        self.apply_mode()

    def apply_mode(self):
        if self.demo and self.mode != "DEMO":
            self.end_demo()
        m = self.mode
        if m == "AUTO":
            self.enter_wait_aos()
        elif m == "MANUAL":
            self.man_az, self.man_el = self.ant_az, self.ant_el
            self.set_state("MANUAL")
        elif m == "DEMO":
            self.enter_demo()
        elif m == "IDLE":
            self.cmd_az, self.cmd_el = self.ant_az, self.ant_el
            self.set_state("IDLE")
        elif m == "STOW":
            self.set_state("STOW")

    def enter_wait_aos(self):
        self.have_raw = False
        self.keyhole = False
        self.set_state("WAIT_AOS")
        if not self.pass_.valid or (self.pass_.sets and self.t_sim > self.pass_.los):
            self.compute_pass(self.t_sim)

    def enter_tracking(self):
        self.have_raw = False
        self.err_sum2 = self.err_max = 0.0
        self.err_n = 0
        self.keyhole = False
        self.emit('{"ev":"AOS","sat":%d,"t_utc":"%s","az":%.1f,"el":%.1f}'
                  % (self.sat_id, P.iso_utc(self.t_sim), self.look.az, self.look.el))
        self.pending_beep = BEEP_AOS
        if self.pass_.valid and self.pass_.sets:
            self.build_plan(self.t_sim, self.plan_az_at(self.t_sim) if self.plan_valid else self.ant_az)
        self.set_state("ACQUIRE")

    def enter_demo(self):
        self.set_state("DEMO")
        p = self.sat.next_pass(self.inp.t_real, C.PASS_SEARCH_H, C.MASK_EL_DEG)
        i = 0
        while i < 30 and p is not None and p.los is not None and p.max_el < C.DEMO_MIN_MAX_EL_DEG:
            p = self.sat.next_pass(p.los + 60.0, C.PASS_SEARCH_H, C.MASK_EL_DEG)
            i += 1
        if p is None or p.los is None or p.max_el < C.DEMO_MIN_MAX_EL_DEG:
            self.emit('{"ev":"ERR","msg":"NO_PASS"}')
            self.mode = "AUTO"
            self.enter_wait_aos()
            return
        self.demo = True
        self.warp = self.demo_warp
        self.anchor_sim = p.aos - C.DEMO_LEAD_S
        self.anchor_ms = self.ms
        self.t_sim = self.anchor_sim
        self.refresh_look(True)
        self.emit('{"ev":"INFO","msg":"DEMO","warp":%d}' % self.warp)
        self.compute_pass(self.t_sim)

    def end_demo(self):
        self.demo = False
        self.warp = 1
        self.t_sim = self.inp.t_real
        self.pass_ = _Pass()
        self.plan_valid = False
        self.refresh_look(True)
        self.emit('{"ev":"INFO","msg":"DEMO_END"}')

    def enter_estop(self):
        if self.demo:
            self.end_demo()
        self.set_state("ESTOP")
        self.emit('{"ev":"ESTOP"}')
        self.pending_beep = BEEP_ERROR
        self.out.drivers_enabled = False
        self.out.relay_on = False
        self.out.stop_now = True
        self.estop_released_said = False

    def enter_fault(self, code):
        if self.demo:
            self.end_demo()
        self.fault = code
        self.set_state("FAULT")
        self.emit('{"ev":"FAULT","code":"%s"}' % code)
        self.pending_beep = BEEP_ERROR
        self.out.drivers_enabled = False
        self.out.relay_on = False
        self.out.stop_now = True

    def ack(self):
        if self.state == "ESTOP":
            if self.inp.estop:
                self.emit('{"ev":"ERR","msg":"ESTOP_ACTIVE"}')
                return
        elif self.state == "FAULT":
            if self.inp.lim_az or self.inp.lim_el:
                self.emit('{"ev":"ERR","msg":"LIMIT_ACTIVE"}')
                return
        else:
            self.emit('{"ev":"ERR","msg":"NOTHING_TO_ACK"}')
            return
        self.emit('{"ev":"ACK"}')
        self.fault = ""
        self.start_homing()

    # ------------------------------------------------------------ commands
    def command(self, line):
        clean = P.sanitize(line)
        try:
            c = P.parse_command(line)
        except ValueError as e:
            self.emit('{"ev":"ERR","cmd":"%s","msg":"%s"}' % (clean, e))
            return
        if c.name == "SAT" and c.args[0] not in self.slots:
            self.emit('{"ev":"ERR","cmd":"%s","msg":"unknown sat"}' % clean)
            return
        if c.name == "JOG" and self.state != "MANUAL":
            self.emit('{"ev":"ERR","cmd":"%s","msg":"not manual"}' % clean)
            return
        self.emit('{"ev":"CMD","cmd":"%s"}' % clean)
        busy = self.state in ("BOOT", "HOMING", "ESTOP", "FAULT")
        n = c.name
        if n == "SAT":
            self.select_sat(c.args[0])
        elif n == "MODE":
            self.mode = c.args[0]
            if not busy:
                self.apply_mode()
        elif n == "WARP":
            self.demo_warp = c.args[0]
            if self.demo:
                self.anchor_sim = self.t_sim
                self.anchor_ms = self.ms
                self.warp = c.args[0]
                if self.state in ("ACQUIRE", "TRACK"):
                    self.build_plan(self.t_sim, self.plan_az_at(self.t_sim) if self.plan_valid else self.cmd_az)
        elif n == "VEH":
            if not c.args:
                self.veh_active = False
            else:
                self.veh_active = True
                self.veh = c.args
                self.veh_ms = self.ms
        elif n == "JOG":
            axis, d = c.args
            if axis == "AZ":
                self.man_az = T.clamp(self.man_az + d, C.AZ_MIN_DEG, C.AZ_MAX_DEG)
            else:
                self.man_el = T.clamp(self.man_el + d, C.EL_MIN_DEG, C.EL_MAX_DEG)
        elif n == "HOME":
            if self.state in ("ESTOP", "FAULT"):
                self.ack()
            elif self.state != "BOOT":
                self.start_homing()
        elif n == "STOW":
            self.mode = "STOW"
            if not busy:
                self.apply_mode()
        elif n == "ACK":
            self.ack()
        elif n == "COMP":
            self.comp = c.args[0]
            if self.state in ("ACQUIRE", "TRACK"):
                self.build_plan(self.t_sim, self.plan_az_at(self.t_sim) if self.plan_valid else self.cmd_az)

    # ------------------------------------------------------------ periodic
    def update_attitude(self, inp):
        if self.veh_active and (inp.ms - self.veh_ms) > int(C.VEH_TIMEOUT_S * 1000.0):
            self.veh_active = False
        if inp.imu_ok:
            dt = (inp.ms - self.imu_ms) / 1000.0 if self.imu_seen else 0.0
            self.filter.update(inp.ax, inp.ay, inp.az, inp.gx, inp.gy, dt)
            self.imu_ms = inp.ms
            self.imu_seen = True
        if self.veh_active:
            self.roll, self.pitch, self.yaw = self.veh
            self.src = "VEH"
        elif self.imu_seen:
            self.roll, self.pitch = self.filter.roll, self.filter.pitch
            self.yaw = C.VEHICLE_YAW_DEFAULT_DEG
            self.src = "MPU"
        else:
            self.roll = self.pitch = 0.0
            self.yaw = C.VEHICLE_YAW_DEFAULT_DEG
            self.src = "NONE"

    def set_targets(self, az, el, v_az, a_az, v_el, a_el):
        self.cmd_az, self.cmd_el = az, el
        o = self.out
        o.az.target = to_steps(az)
        o.el.target = to_steps(el)
        o.az.max_speed_dps, o.az.accel_dps2 = v_az, a_az
        o.el.max_speed_dps, o.el.accel_dps2 = v_el, a_el

    def pointing_tick(self):
        enu = self.sat_enu_at(self.t_sim)
        az_s, el_s = G.enu_to_azel(enu)
        p_az, p_el = G.pointing_command(az_s, el_s, self.roll, self.pitch, self.yaw, self.comp)
        if not self.have_raw:
            ref = self.plan_az_at(self.t_sim) if self.plan_valid else self.ant_az
            self.raw_az = T.unwrap_near(ref, p_az)
            self.raw_ms = self.ms
            self.req_rate = 0.0
            self.have_raw = True
        else:
            nr = T.unwrap_near(self.raw_az, p_az)
            dt = (self.ms - self.raw_ms) / 1000.0
            if dt > 0:
                self.req_rate = abs(nr - self.raw_az) / dt
            self.raw_az = nr
            self.raw_ms = self.ms
        lead = self.plan_lead_at(self.t_sim)
        az = self.raw_az + lead
        if az > C.AZ_MAX_DEG or az < C.AZ_MIN_DEG:
            shift = -360.0 if az > C.AZ_MAX_DEG else 360.0
            self.emit('{"ev":"WRAP","from":%.1f,"to":%.1f}' % (az, az + shift))
            self.raw_az += shift
            az += shift
            self.plan_valid = False
        az = T.clamp(az, C.AZ_MIN_DEG, C.AZ_MAX_DEG)
        el = T.clamp(p_el, C.EL_MIN_DEG, C.EL_MAX_DEG)
        self.set_targets(az, el, C.AZ_MAX_SPEED_DPS, C.AZ_ACCEL_DPS2, C.EL_MAX_SPEED_DPS, C.EL_ACCEL_DPS2)
        cond = self.err > C.KEYHOLE_ERR_DEG and (abs(lead) > 0.5 * C.KEYHOLE_ERR_DEG
                                                 or self.req_rate > 0.95 * C.AZ_MAX_SPEED_DPS)
        if cond != self.keyhole and (self.ms - self.kh_ms) > 1000:
            self.keyhole = cond
            self.kh_ms = self.ms
            if cond:
                self.kh_zenith = self.look.el > C.KEYHOLE_EL_DEG
            self.emit('{"ev":"%s","on":%d,"err":%.2f,"req_dps":%.1f}'
                      % ("KEYHOLE" if self.kh_zenith else "RATE_LIMIT", 1 if cond else 0,
                         self.err, self.req_rate))

    def update(self, inp):
        self.inp = inp
        self.ms = inp.ms
        o = self.out
        o.az.set_pos = o.el.set_pos = False
        o.stop_now = False
        o.beep = BEEP_NONE
        o.tle_request = 0

        if self.demo:
            if self.state == "DEMO":
                self.anchor_ms = inp.ms
                self.t_sim = self.anchor_sim
            else:
                self.t_sim = self.anchor_sim + self.warp * (inp.ms - self.anchor_ms) / 1000.0
        else:
            self.t_sim = inp.t_real

        self.ant_az = inp.az_steps / C.STEPS_PER_DEG
        self.ant_el = inp.el_steps / C.STEPS_PER_DEG
        self.update_attitude(inp)

        if inp.estop and self.state not in ("ESTOP", "BOOT"):
            self.enter_estop()
        if not inp.lim_az:
            self.lim_armed_az = True
        if not inp.lim_el:
            self.lim_armed_el = True
        lim_check = self.state not in ("BOOT", "HOMING", "ESTOP", "FAULT")
        if lim_check and inp.lim_az and self.lim_armed_az:
            self.enter_fault("LIMIT_AZ")
        elif lim_check and inp.lim_el and self.lim_armed_el:
            self.enter_fault("LIMIT_EL")

        if inp.btn_home:
            if self.state in ("ESTOP", "FAULT"):
                self.ack()
            elif self.state != "BOOT":
                self.start_homing()
        busy = self.state in ("BOOT", "HOMING", "ESTOP", "FAULT")
        if inp.btn_stow and not busy:
            self.mode = "STOW"
            self.apply_mode()
        if inp.btn_mode and not busy:
            self.mode = {"AUTO": "MANUAL", "MANUAL": "DEMO"}.get(self.mode, "AUTO")
            self.apply_mode()
        if inp.encoder_press and self.state == "MANUAL":
            self.man_axis_el = not self.man_axis_el

        if self.tick % (C.CONTROL_HZ // C.SAT_HZ) == 0 or self.look is None:
            self.refresh_look(False)
        if self.look is not None:
            enu = self.sat_enu_at(self.t_sim)
            self.err = G.angle_between(
                G.boresight_enu(self.ant_az, self.ant_el, self.roll, self.pitch, self.yaw), enu)

        st = self.state
        if st == "BOOT":
            o.drivers_enabled = False
            o.relay_on = False
        elif st == "HOMING":
            az_trig = inp.lim_az or (self.sim_limits and self.az_start - inp.az_steps >= C.SIM_HOME_AZ_STEPS)
            el_trig = inp.lim_el or (self.sim_limits and self.el_start - inp.el_steps >= C.SIM_HOME_EL_STEPS)
            if not self.az_homed and az_trig:
                self.az_homed = True
                o.az.target = to_steps(C.AZ_HOME_DEG)
                o.az.set_pos = True
                self.lim_armed_az = not inp.lim_az
            if not self.el_homed and el_trig:
                self.el_homed = True
                o.el.target = to_steps(C.EL_HOME_DEG)
                o.el.set_pos = True
                self.lim_armed_el = not inp.lim_el
            if self.az_homed and self.el_homed:
                self.ant_az, self.ant_el = C.AZ_HOME_DEG, C.EL_HOME_DEG
                self.cmd_az, self.cmd_el = C.AZ_HOME_DEG, C.EL_HOME_DEG
                self.after_homing()
            elif inp.ms - self.home_start_ms > int(C.HOMING_TIMEOUT_S * 1000.0):
                self.enter_fault("HOMING_TIMEOUT")
        elif st == "IDLE":
            self.set_targets(self.cmd_az, self.cmd_el, C.AZ_MAX_SPEED_DPS, C.AZ_ACCEL_DPS2,
                             C.EL_MAX_SPEED_DPS, C.EL_ACCEL_DPS2)
        elif st == "STOW":
            self.set_targets(C.STOW_AZ_DEG, C.STOW_EL_DEG, C.AZ_MAX_SPEED_DPS, C.AZ_ACCEL_DPS2,
                             C.EL_MAX_SPEED_DPS, C.EL_ACCEL_DPS2)
        elif st == "MANUAL":
            v = 1.0 + T.clamp(inp.pot_frac, 0.0, 1.0) * (C.MANUAL_MAX_SPEED_DPS - 1.0)
            if inp.encoder_delta:
                if self.man_axis_el:
                    self.man_el = T.clamp(self.man_el + 0.5 * inp.encoder_delta, C.EL_MIN_DEG, C.EL_MAX_DEG)
                else:
                    self.man_az = T.clamp(self.man_az + 0.5 * inp.encoder_delta, C.AZ_MIN_DEG, C.AZ_MAX_DEG)
            self.set_targets(self.man_az, self.man_el, v, C.AZ_ACCEL_DPS2, v, C.EL_ACCEL_DPS2)
        elif st == "DEMO":
            if not self.plan_valid:
                self.end_demo()
                self.mode = "AUTO"
                self.enter_wait_aos()
            else:
                self.set_targets(self.plan_start_az, self.plan_start_el, C.AZ_MAX_SPEED_DPS,
                                 C.AZ_ACCEL_DPS2, C.EL_MAX_SPEED_DPS, C.EL_ACCEL_DPS2)
                if abs(self.ant_az - self.plan_start_az) < 0.5 and abs(self.ant_el - self.plan_start_el) < 0.5:
                    self.anchor_ms = inp.ms
                    self.set_state("WAIT_AOS")
        elif st == "WAIT_AOS":
            ps = self.pass_
            stale = not ps.valid or (ps.sets and self.t_sim > ps.los + 1.0)
            if stale and (not self.pass_tried or (self.ms - self.pass_try_ms) > 10000):
                self.compute_pass(self.t_sim)
            if self.look is not None and self.look.el > C.MASK_EL_DEG:
                self.enter_tracking()
                self.pointing_tick()
            elif self.pass_.valid and self.plan_valid and self.pass_.aos - self.t_sim <= C.PREPOSITION_LEAD_S:
                self.set_targets(self.plan_start_az, self.plan_start_el, C.AZ_MAX_SPEED_DPS,
                                 C.AZ_ACCEL_DPS2, C.EL_MAX_SPEED_DPS, C.EL_ACCEL_DPS2)
            else:
                self.set_targets(C.STOW_AZ_DEG, C.STOW_EL_DEG, C.AZ_MAX_SPEED_DPS, C.AZ_ACCEL_DPS2,
                                 C.EL_MAX_SPEED_DPS, C.EL_ACCEL_DPS2)
        elif st in ("ACQUIRE", "TRACK"):
            if self.look is None or self.look.el <= C.MASK_EL_DEG:
                rms = math.sqrt(self.err_sum2 / self.err_n) if self.err_n else 0.0
                self.emit('{"ev":"LOS","sat":%d,"t_utc":"%s","max_err":%.3f,"rms_err":%.3f,'
                          '"n":%d,"comp":%d,"warp":%d}'
                          % (self.sat_id, P.iso_utc(self.t_sim), self.err_max, rms, self.err_n,
                             1 if self.comp else 0, self.warp if self.demo else 1))
                self.pending_beep = BEEP_LOS
                if self.demo:
                    self.end_demo()
                    self.mode = "AUTO"
                self.pass_ = _Pass()
                self.pass_tried = False
                self.enter_wait_aos()
            else:
                self.pointing_tick()
                if self.state == "ACQUIRE" and self.err < C.ACQUIRE_ERR_DEG:
                    self.set_state("TRACK")
                if self.state == "TRACK":
                    self.err_sum2 += self.err * self.err
                    self.err_n += 1
                    self.err_max = max(self.err_max, self.err)
        elif st == "ESTOP":
            o.drivers_enabled = False
            o.relay_on = False
            if not inp.estop and not self.estop_released_said:
                self.emit('{"ev":"INFO","msg":"ESTOP_RELEASED_PRESS_HOME"}')
                self.estop_released_said = True
        elif st == "FAULT":
            o.drivers_enabled = False
            o.relay_on = False

        if self.state not in ("BOOT", "ESTOP", "FAULT"):
            o.drivers_enabled = True
            o.relay_on = True
        if self.pending_tle:
            o.tle_request = self.pending_tle
            self.pending_tle = 0
        o.beep = self.pending_beep
        self.pending_beep = BEEP_NONE
        self.leds()
        if self.tick % (C.CONTROL_HZ // C.TELEMETRY_HZ) == 0:
            self.telemetry()
        self.tick += 1
        return o

    def leds(self):
        blink = ((self.ms // 250) & 1) != 0
        st = self.state
        if st == "TRACK":
            v = LED_GREEN
        elif st == "ACQUIRE":
            v = LED_GREEN if blink else 0
        elif st == "HOMING":
            v = LED_YELLOW if blink else 0
        elif st == "ESTOP":
            v = LED_RED
        elif st == "FAULT":
            v = LED_RED if blink else 0
        else:
            v = LED_YELLOW
        self.out.leds = v

    def tle_age_days(self):
        return self.sat.age_days(self.t_sim) if self.sat else 0.0

    def telemetry(self):
        ps = self.pass_
        aos = _fmt_iso_or_null(ps.aos, ps.valid)
        los = _fmt_iso_or_null(ps.los, ps.valid and ps.sets)
        max_el = "%.1f" % ps.max_el if ps.valid else "null"
        lk = self.look
        s_az = lk.az if lk else 0.0
        s_el = lk.el if lk else 0.0
        rng = lk.range_km if lk else 0.0
        self.emit(
            '{"t_utc":"%s","sat":%d,"sat_az":%.2f,"sat_el":%.2f,"range_km":%.1f,'
            '"cmd_az":%.2f,"cmd_el":%.2f,"ant_az":%.2f,"ant_el":%.2f,"roll":%.2f,'
            '"pitch":%.2f,"yaw":%.2f,"err_deg":%.3f,"mode":"%s","next_aos":%s,'
            '"next_los":%s,"max_el":%s,"warp":%d,"comp":%d,"kh":%d,"src":"%s",'
            '"tle_age":%.1f,"tle_fb":%d,"axis":"%s"}'
            % (P.iso_utc(self.t_sim), self.sat_id, s_az, s_el, rng, self.cmd_az, self.cmd_el,
               self.ant_az, self.ant_el, self.roll, self.pitch, self.yaw, self.err, self.state,
               aos, los, max_el, self.warp if self.demo else 1, 1 if self.comp else 0,
               1 if self.keyhole else 0, self.src, self.tle_age_days(),
               1 if self.tle_fallback() else 0, "EL" if self.man_axis_el else "AZ"))
