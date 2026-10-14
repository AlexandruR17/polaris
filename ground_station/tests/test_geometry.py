import math

import numpy as np
import pytest

from polaris_gs.core import geometry as G


def ped(sat_az, sat_el, roll=0.0, pitch=0.0, yaw=90.0):
    return G.pointing_command(sat_az, sat_el, roll, pitch, yaw)


def close_az(a, b, tol=1e-6):
    return abs(G.wrap180(a - b)) < tol


def test_rotation_is_orthonormal():
    R = G.attitude_matrix(7.0, -12.0, 33.0)
    assert np.allclose(R.T @ R, np.eye(3))
    assert np.isclose(np.linalg.det(R), 1.0)


def test_no_tilt_facing_north_is_identity_in_azimuth():
    for az in (0, 45, 90, 135, 180, 225, 270, 315):
        for el in (5, 30, 60, 89):
            a, e = ped(az, el)
            assert close_az(a, az)
            assert e == pytest.approx(el, abs=1e-9)


def test_no_tilt_facing_east_shifts_azimuth():
    a, e = ped(90.0, 20.0, yaw=0.0)
    assert close_az(a, 0.0) and e == pytest.approx(20.0)
    a, e = ped(180.0, 20.0, yaw=0.0)
    assert close_az(a, 90.0)


def test_roll_10_zenith_leans_left():
    # positive roll lifts the left side, the zenith is seen to the left
    a, e = ped(0.0, 90.0, roll=10.0)
    assert close_az(a, -90.0)
    assert e == pytest.approx(80.0, abs=1e-9)


def test_roll_10_side_target():
    # target due east (right of a north facing vehicle) at el 0:
    # the right side is down, so the target appears 10 deg higher
    a, e = ped(90.0, 0.0, roll=10.0)
    assert close_az(a, 90.0)
    assert e == pytest.approx(10.0, abs=1e-9)


def test_pitch_10_nose_down():
    # nose down 10 deg: north horizon appears at +10 deg elevation
    a, e = ped(0.0, 0.0, pitch=10.0)
    assert close_az(a, 0.0)
    assert e == pytest.approx(10.0, abs=1e-9)
    a, e = ped(0.0, 90.0, pitch=10.0)
    assert close_az(a, 180.0)
    assert e == pytest.approx(80.0, abs=1e-9)


def test_combined_roll_pitch_matches_closed_form():
    r, p = 10.0, 10.0
    b = G.enu_to_body([0, 0, 1], r, p, 90.0)
    expected = G.gravity_in_body(r, p)
    assert np.allclose(b, expected)
    a, e = G.body_to_pedestal(b)
    rr, pp = math.radians(r), math.radians(p)
    assert e == pytest.approx(math.degrees(math.asin(math.cos(pp) * math.cos(rr))), abs=1e-9)
    assert a == pytest.approx(math.degrees(math.atan2(-math.cos(pp) * math.sin(rr), -math.sin(pp))), abs=1e-9)


@pytest.mark.parametrize("r,p,y", [(0, 0, 0), (10, 0, 90), (0, 10, 90), (10, 10, 90), (-7, 4, 213), (20, -15, 5)])
def test_compensated_pointing_has_zero_error(r, p, y):
    for az, el in ((10, 10), (100, 45), (250, 80), (333, 5)):
        a, e = G.pointing_command(az, el, r, p, y, compensate=True)
        assert G.pointing_error(a, e, r, p, y, az, el) < 1e-6


def test_uncompensated_error_equals_tilt_at_zenith():
    a, e = G.pointing_command(0, 90, 10, 0, 90, compensate=False)
    assert G.pointing_error(a, e, 10, 0, 90, 0, 90) == pytest.approx(10.0, abs=1e-6)


def test_accel_roll_pitch_roundtrip():
    for r, p in ((0, 0), (10, 0), (0, 10), (-12, 7), (30, -20)):
        ax, ay, az = G.gravity_in_body(r, p)
        rr, pp = G.accel_to_roll_pitch(ax, ay, az)
        assert rr == pytest.approx(r, abs=1e-9)
        assert pp == pytest.approx(p, abs=1e-9)


def test_wrap180():
    assert G.wrap180(190) == pytest.approx(-170)
    assert G.wrap180(-190) == pytest.approx(170)
    assert G.wrap180(180) == pytest.approx(-180)
