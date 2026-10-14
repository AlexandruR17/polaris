import math

import pytest

from polaris_gs.core import config as C
from polaris_gs.core import tracking as T


def zenith_pass(miss_deg, n=301, dt=1.0):
    """Synthetic straight overhead pass: az flips near the zenith."""
    out_az, out_el = [], []
    for i in range(n):
        x = (i - n // 2) * 0.05          # along track
        y = math.tan(math.radians(miss_deg))
        az = math.degrees(math.atan2(y, x)) % 360.0
        el = math.degrees(math.atan2(1.0, math.hypot(x, y)))
        out_az.append(az)
        out_el.append(el)
    return out_az, out_el, dt


def test_unwrap_near():
    assert T.unwrap_near(350, 5) == pytest.approx(365)
    assert T.unwrap_near(-170, 175) == pytest.approx(-185)
    assert T.unwrap_near(0, 90) == pytest.approx(90)


def test_wrap_crossing_north_is_continuous():
    seq = [340, 350, 359, 5, 15, 25]
    off, ok = T.plan_wrap([T.unwrap_near(0, a) for a in seq], current_az=0.0)
    assert ok
    path = [a + off for a in T.unwrap_sequence(seq)]
    assert max(abs(path[i] - path[i - 1]) for i in range(1, len(path))) < 20


def test_wrap_choice_respects_cable_limits():
    # antenna parked at +250, pass sweeps 100 -> 300 clockwise
    seq = [100 + i for i in range(0, 201, 10)]
    off, ok = T.plan_wrap(seq, current_az=250.0)
    assert ok
    path = [a + off for a in T.unwrap_sequence(seq)]
    assert min(path) >= C.AZ_MIN_DEG and max(path) <= C.AZ_MAX_DEG
    assert path[0] == pytest.approx(-260.0)


def test_wrap_prefers_closest_start():
    seq = [-30, -20, -10, 0, 10]
    off, ok = T.plan_wrap(seq, current_az=330.0 - 360.0)
    assert ok and off == 0.0
    # +360 would end at 370, outside the cable range: keep 0
    off, ok = T.plan_wrap(seq, current_az=200.0)
    assert ok and off == 0.0
    off, ok = T.plan_wrap([-150, -140, -130], current_az=200.0)
    assert ok and off == 360.0


def test_keyhole_detected_and_rate_limited():
    az, el, dt = zenith_pass(miss_deg=2.0)
    seq = T.unwrap_sequence(az)
    vmax = 10.0
    assert T.max_rate(seq, dt) > vmax       # keyhole: required rate too high
    prof = T.rate_limit_fwd_bwd(seq, dt, vmax)
    assert T.max_rate(prof, dt) <= vmax + 1e-9
    # anticipation: profile starts moving before the raw path does
    i_mid = len(seq) // 2
    dev = [abs(p - s) for p, s in zip(prof, seq)]
    first_dev = next(i for i, d in enumerate(dev) if d > 0.5)
    assert first_dev < i_mid
    # error spread on both sides: peak error lower than the forward-only limiter
    fwd = [seq[0]]
    for v in seq[1:]:
        fwd.append(fwd[-1] + max(-vmax * dt, min(vmax * dt, v - fwd[-1])))
    assert max(dev) < max(abs(f - s) for f, s in zip(fwd, seq))


def test_slow_pass_unchanged_by_planner():
    seq = [100 + 0.2 * i for i in range(200)]
    prof = T.rate_limit_fwd_bwd(seq, 1.0, 5.0)
    assert max(abs(a - b) for a, b in zip(prof, seq)) < 1e-9


def test_axis_model_reaches_target_with_limits():
    ax = T.Axis(C.AZ_MAX_SPEED_DPS, C.AZ_ACCEL_DPS2)
    ax.move_to(90.0 * C.STEPS_PER_DEG)
    t, dt, vmax_seen = 0.0, 0.001, 0.0
    while abs(ax.deg - 90.0) > 0.01 or ax.speed != 0.0:
        ax.run(dt)
        vmax_seen = max(vmax_seen, abs(ax.speed))
        t += dt
        assert t < 10
    assert vmax_seen <= ax.max_speed + 1e-9
    # trapezoid: 90 deg at 40 dps, 120 dps2 -> about 2.58 s
    assert t == pytest.approx(90 / 40 + 40 / 120, abs=0.05)


def test_resolution():
    assert C.STEPS_PER_DEG == pytest.approx(16000 / 360)
    assert C.DEG_PER_STEP == pytest.approx(0.0225)
