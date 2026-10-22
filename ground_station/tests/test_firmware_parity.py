"""The firmware core compiled natively with g++ against the Python reference.

Needs g++ and make. The harness is built from firmware/test_native.
"""
import datetime as dt
import json
import math
import pathlib
import random
import re
import shutil
import subprocess

import pytest
import sgp4 as sgp4_pkg
from skyfield.api import EarthSatellite, load, wgs84

from polaris_gs.core import config as C
from polaris_gs.core import geometry as G
from polaris_gs.core import protocol as P
from polaris_gs.core import tracking as T
from polaris_gs.core.orbit import Satellite, gmst_rad
from polaris_gs.core.tle_data import FALLBACK_TLE
from polaris_gs.sim.runner import run_scenario

ROOT = pathlib.Path(__file__).resolve().parents[2]
NATIVE = ROOT / "firmware" / "test_native"
HARNESS = NATIVE / "build" / "harness"
SCENARIOS = sorted((NATIVE / "scenarios").glob("*.txt"))

pytestmark = pytest.mark.skipif(shutil.which("g++") is None or shutil.which("make") is None,
                                reason="g++/make not available")


@pytest.fixture(scope="module", autouse=True)
def harness():
    subprocess.run(["make", "-C", str(NATIVE)], check=True, capture_output=True)
    return HARNESS


def run(mode, text):
    r = subprocess.run([str(HARNESS), mode], input=text, capture_output=True, text=True, check=True)
    return r.stdout.splitlines()


# ------------------------------------------------------------ mirrors
def test_config_h_matches_config_py():
    src = (ROOT / "firmware/lib/polaris_core/pc_config.h").read_text()
    found = dict(re.findall(r"constexpr \w+ (\w+) = ([^;]+);", src))
    checked = 0
    for name, expr in found.items():
        if not hasattr(C, name):
            continue
        val = eval(expr.replace("MOTOR_STEPS_PER_REV", str(C.MOTOR_STEPS_PER_REV))
                   .replace("MICROSTEPS", str(C.MICROSTEPS)).replace("GEAR_RATIO", str(C.GEAR_RATIO))
                   .replace("STEPS_PER_DEG", str(C.STEPS_PER_DEG)))
        assert val == pytest.approx(getattr(C, name)), name
        checked += 1
    assert checked >= 40
    assert re.search(r'#define FW_VERSION "([^"]+)"', src).group(1) == C.FW_VERSION


def test_fallback_tle_header_matches_python():
    src = (ROOT / "firmware/lib/polaris_core/pc_tle_fallback.h").read_text()
    entries = re.findall(r'\{(\d+), "([^"]*)",\s*"([^"]+)",\s*"([^"]+)"\}', src)
    assert len(entries) == len(FALLBACK_TLE)
    for cat, _, l1, l2 in entries:
        assert FALLBACK_TLE[int(cat)][1:] == (l1, l2)


# ------------------------------------------------------------ SGP4
def test_firmware_sgp4_matches_vallado_verification_vectors():
    pkg = pathlib.Path(sgp4_pkg.__file__).parent
    ver_tle, ver_out = pkg / "SGP4-VER.TLE", pkg / "tcppver.out"
    if not ver_tle.exists():
        pytest.skip("verification files not shipped with sgp4")
    ref, sat = {}, None
    for ln in ver_out.read_text().splitlines():
        p = ln.split()
        if len(p) == 2 and p[1] == "xx":
            sat = int(p[0])
        elif len(p) >= 4:
            ref[(sat, round(float(p[0]), 4))] = tuple(map(float, p[1:4]))
    worst, n = 0.0, 0
    for ln in run("sgp4ver", ver_tle.read_text()):
        p = ln.split()
        if len(p) < 5:
            continue
        k = (int(p[0]), round(float(p[1]), 4))
        if k in ref:
            d = math.dist(tuple(map(float, p[2:5])), ref[k])
            worst = max(worst, d)
            n += 1
    assert n > 600
    assert worst < 1e-5  # km, i.e. 1 cm


# ------------------------------------------------------------ math
def test_pointing_math_matches():
    rnd = random.Random(1)
    q = []
    for _ in range(300):
        q.append((rnd.uniform(0, 360), rnd.uniform(-5, 90), rnd.uniform(-30, 30),
                  rnd.uniform(-30, 30), rnd.uniform(-180, 180), rnd.choice((0, 1))))
    out = run("math", "".join("point %r %r %r %r %r %d\n" % x for x in q))
    for x, line in zip(q, out):
        az, el, err = map(float, line.split())
        paz, pel = G.pointing_command(*x[:5], compensate=bool(x[5]))
        assert abs(G.wrap180(az - paz)) < 1e-9 and abs(el - pel) < 1e-9
        assert err < 1e-6 if x[5] else True


def test_roll_pitch_from_accel_matches():
    rnd = random.Random(2)
    q = [(rnd.uniform(-0.5, 0.5), rnd.uniform(-0.5, 0.5), rnd.uniform(0.7, 1.1)) for _ in range(50)]
    out = run("math", "".join("rp %r %r %r\n" % x for x in q))
    for x, line in zip(q, out):
        r, p = map(float, line.split())
        pr, pp = G.accel_to_roll_pitch(*x)
        assert r == pytest.approx(pr, abs=1e-12) and p == pytest.approx(pp, abs=1e-12)


def test_gmst_and_iso_match():
    rnd = random.Random(3)
    jds = [2461000.5 + rnd.uniform(0, 1000) for _ in range(20)]
    out = run("math", "".join("gmst %r\n" % j for j in jds))
    for j, line in zip(jds, out):
        assert float(line) == pytest.approx(gmst_rad(j), abs=1e-12)
    ts = [1792015503.0, 1792015503.95, 0.0, 1786937667.04, 4102444799.9]
    out = run("math", "".join("iso %r\n" % t for t in ts))
    assert out == [P.iso_utc(t) for t in ts]


@pytest.mark.parametrize("catnr", list(FALLBACK_TLE))
def test_look_angles_match_python_and_skyfield(catnr):
    name, l1, l2 = FALLBACK_TLE[catnr]
    py = Satellite(name, l1, l2)
    ts_sky = load.timescale(builtin=True)
    site = wgs84.latlon(C.STATION_LAT_DEG, C.STATION_LON_DEG, elevation_m=C.STATION_ALT_M)
    es = EarthSatellite(l1, l2, name, ts_sky)
    times = [py.epoch_unix + k * 997.0 for k in range(200)]
    out = run("math", "".join("look %d %r\n" % (catnr, t) for t in times))
    worst_py = worst_sky = 0.0
    for t, line in zip(times, out):
        az, el, rng = map(float, line.split())
        lk = py.look(t)
        v = G.azel_to_enu(az, el)
        worst_py = max(worst_py, G.angle_between(v, G.azel_to_enu(lk.az, lk.el)))
        alt, saz, _ = (es - site).at(ts_sky.from_datetime(
            dt.datetime.fromtimestamp(t, dt.timezone.utc))).altaz()
        if alt.degrees > -5:
            worst_sky = max(worst_sky, G.angle_between(v, G.azel_to_enu(saz.degrees, alt.degrees)))
    assert worst_py < 1e-6
    assert worst_sky < 0.1


@pytest.mark.parametrize("catnr", [25544, 33591, 43700])
def test_pass_prediction_matches(catnr):
    py = Satellite(*FALLBACK_TLE[catnr])
    times = [py.epoch_unix + k * 7777.0 for k in range(8)]
    out = run("math", "".join("pass %d %r\n" % (catnr, t) for t in times))
    for t, line in zip(times, out):
        valid, aos, los, sets, tmax, max_el, aos_az = line.split()
        p = py.next_pass(t)
        assert (valid == "1") == (p is not None)
        if p is None:
            continue
        assert float(aos) == pytest.approx(p.aos, abs=1.0)
        assert (sets == "1") == (p.los is not None)
        if p.los is not None:
            assert float(los) == pytest.approx(p.los, abs=1.0)
            assert float(max_el) == pytest.approx(p.max_el, abs=0.01)


def test_wrap_and_rate_limit_match():
    rnd = random.Random(4)
    for _ in range(30):
        n = rnd.randint(5, 40)
        start = rnd.uniform(-180, 180)
        seq = [start]
        for _ in range(n - 1):
            seq.append(seq[-1] + rnd.uniform(-20, 20))
        cur = rnd.uniform(-270, 270)
        wrapped = [G.wrap180(a) for a in seq]
        line = run("math", "wrap %r %d %s\n" % (cur, n, " ".join(repr(a) for a in wrapped)))[0]
        off, ok = line.split()
        poff, pok = T.plan_wrap(wrapped, cur)
        assert float(off) == pytest.approx(poff) and (ok == "1") == pok
        line = run("math", "ratelim 1.0 7.5 %d %s\n" % (n, " ".join(repr(a) for a in seq)))[0]
        got = list(map(float, line.split()))
        assert got == pytest.approx(T.rate_limit_fwd_bwd(seq, 1.0, 7.5), abs=1e-9)


# ------------------------------------------------------------ protocol
COMMANDS = ["SAT:25544", "sat:33591", " MODE : demo ", "MODE:FAST", "WARP:30", "WARP:7", "WARP:",
            "VEH:1.5,-2.25,90", "VEH:off", "VEH:1,2", "VEH:50,0,0", "VEH:a,b,c", "VEH:nan,0,0",
            "JOG:az,-12.5", "JOG:EL,90", "JOG:EL,90.5", "JOG:XY,1", "HOME", "HOME:1", "STOW", "ACK", "TLE", "tle", "TLE:1",
            "COMP:0", "COMP:1", "COMP:2", "", "FOO", "SAT:", "SAT:12a", "SAT:1234567890"]


def py_parse(line):
    try:
        c = P.parse_command(line)
    except ValueError as e:
        return f"ERR {e}"
    if c.name == "VEH":
        return "VEH OFF" if not c.args else "VEH %.6f %.6f %.6f" % c.args
    if c.name == "JOG":
        return "JOG %s %.6f" % c.args
    if c.name == "COMP":
        return "COMP %d" % c.args[0]
    if c.args:
        return f"{c.name} {c.args[0]}"
    return c.name


def test_command_parser_matches():
    out = run("parse", "".join(c + "\n" for c in COMMANDS))
    assert out == [py_parse(c) for c in COMMANDS]


# ------------------------------------------------------------ full state machine
def split(lines):
    ev, tel = [], []
    for ln in lines:
        ms, _, js = ln.partition(" ")
        d = json.loads(js)
        (ev if "ev" in d else tel).append((int(ms), d))
    return ev, tel


AZ_EL_PAIR = {"sat_az": "sat_el", "cmd_az": "cmd_el", "ant_az": "ant_el", "az": "el"}


def close(a, b, key, rec=None):
    iso = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\dZ$")
    if isinstance(a, str) and isinstance(b, str) and iso.match(a) and iso.match(b):
        return abs(P.parse_iso_utc(a) - P.parse_iso_utc(b)) <= 1.5
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if key == "req_dps":  # ill-conditioned near the zenith
            return abs(a - b) <= 0.05 * max(abs(a), abs(b)) + 0.2
        one_decimal = ("az", "el", "max_el", "aos_az", "from", "to", "age_d", "tle_age", "t_s")
        tol = 1.0 if key == "range_km" else (0.11 if key in one_decimal else 0.06)
        if key in ("sat_az", "aos_az", "cmd_az", "ant_az", "az"):
            # compare as distance on the sky: azimuth is ill-defined near the zenith
            el = rec.get(AZ_EL_PAIR.get(key, ""), 0.0) if rec else 0.0
            return abs(G.wrap180(a - b)) * math.cos(math.radians(min(abs(el), 90.0))) <= tol
        return abs(a - b) <= tol
    return a == b


@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_state_machine_same_events_and_telemetry(path):
    text = path.read_text()
    cpp_ev, cpp_tel = split(run("scenario", text))
    py_ev, py_tel = split(run_scenario(text))
    assert [e["ev"] for _, e in cpp_ev] == [e["ev"] for _, e in py_ev]
    for (mc, ec), (mp, ep) in zip(cpp_ev, py_ev):
        assert abs(mc - mp) <= 40, (ec, ep)
        assert ec.keys() == ep.keys()
        for k in ec:
            assert close(ec[k], ep[k], k, ec), (k, ec, ep)
    assert len(cpp_tel) == len(py_tel)
    assert [t["mode"] for _, t in cpp_tel] == [t["mode"] for _, t in py_tel]
    bad = 0
    for (_, a), (_, b) in zip(cpp_tel, py_tel):
        for k in a:
            if not close(a[k], b[k], k, a):
                bad += 1
    # a handful of samples may straddle a step boundary
    assert bad <= len(cpp_tel) // 100 + 2


def test_pass_search_never_blocks_a_control_tick(monkeypatch):
    """On the ESP32 one SGP4 call in double precision costs about a millisecond:
    a whole 24 h pass search in one tick starved the task watchdog in Wokwi.
    The search is now spread over ticks; no tick may run more than a few
    hundred propagations (the coarse budget plus one refinement)."""
    from polaris_gs.core import orbit as O
    from polaris_gs.sim.runner import DT_MS, SimRig

    calls = [0]
    real = O.Satellite.elevation

    def counting(self, t):
        calls[0] += 1
        return real(self, t)

    monkeypatch.setattr(O.Satellite, "elevation", counting)
    events = []
    t0 = 1792015503.0
    rig = SimRig(events.append, t0)
    rig.inp.ms, rig.inp.t_real = 0, t0
    rig.ctl.boot_done(rig.inp)
    worst, ms = 0, 0
    for i in range(2500):                      # 50 s: homing, pass search, then DEMO
        ms += DT_MS
        if i == 600:
            rig.ctl.command("MODE:DEMO")
        calls[0] = 0
        rig.step(ms, t0 + ms / 1000.0)
        worst = max(worst, calls[0])
    assert any('"ev":"PASS"' in e for e in events)
    assert any('"msg":"DEMO"' in e for e in events)
    assert worst <= 150, worst
