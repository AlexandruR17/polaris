"""Our SGP4 + TEME->ENU chain against skyfield (independent implementation)."""
import pytest
from skyfield.api import EarthSatellite, load, wgs84

from polaris_gs.core import config as C
from polaris_gs.core import geometry as G
from polaris_gs.core.orbit import Satellite, tle_checksum_ok
from polaris_gs.core.tle_data import FALLBACK_TLE

TS = load.timescale(builtin=True)
SITE = wgs84.latlon(C.STATION_LAT_DEG, C.STATION_LON_DEG, elevation_m=C.STATION_ALT_M)


def sky_look(name, l1, l2, t_unix):
    sat = EarthSatellite(l1, l2, name, TS)
    t = TS.from_datetime(__import__("datetime").datetime.fromtimestamp(t_unix, __import__("datetime").timezone.utc))
    alt, az, dist = (sat - SITE).at(t).altaz()
    return az.degrees, alt.degrees, dist.km


@pytest.mark.parametrize("catnr", list(FALLBACK_TLE))
def test_fallback_tle_checksums(catnr):
    _, l1, l2 = FALLBACK_TLE[catnr]
    assert tle_checksum_ok(l1) and tle_checksum_ok(l2)


@pytest.mark.parametrize("catnr", list(FALLBACK_TLE))
def test_against_skyfield_below_0_1_deg(catnr):
    name, l1, l2 = FALLBACK_TLE[catnr]
    sat = Satellite(name, l1, l2)
    worst = 0.0
    checked = 0
    t = sat.epoch_unix
    while t < sat.epoch_unix + 2 * 86400:
        lk = sat.look(t)
        az, el, rng = sky_look(name, l1, l2, t)
        if el > -5:
            d = G.angle_between(G.azel_to_enu(lk.az, lk.el), G.azel_to_enu(az, el))
            worst = max(worst, d)
            assert abs(lk.range_km - rng) / rng < 1e-3
            checked += 1
        t += 37.0 if el > -5 else 300.0
    assert checked > 5
    assert worst < 0.1, f"worst difference {worst:.4f} deg"


def test_pass_prediction_iss_matches_skyfield_events():
    name, l1, l2 = FALLBACK_TLE[25544]
    sat = Satellite(name, l1, l2)
    t0 = sat.epoch_unix
    passes = sat.passes(t0, count=4)
    assert len(passes) == 4
    es = EarthSatellite(l1, l2, name, TS)
    import datetime as dt
    t_a = TS.from_datetime(dt.datetime.fromtimestamp(t0, dt.timezone.utc))
    t_b = TS.from_datetime(dt.datetime.fromtimestamp(passes[-1].los + 60, dt.timezone.utc))
    times, events = es.find_events(SITE, t_a, t_b, altitude_degrees=C.MASK_EL_DEG)
    rises = [t.utc_datetime().timestamp() for t, e in zip(times, events) if e == 0]
    sets = [t.utc_datetime().timestamp() for t, e in zip(times, events) if e == 2]
    for p, r, s in zip(passes, rises, sets):
        assert abs(p.aos - r) < 5.0
        assert abs(p.los - s) < 5.0
        assert C.MASK_EL_DEG < p.max_el <= 90.0
        assert p.aos < p.tmax < p.los


def test_geostationary_never_sets():
    name, l1, l2 = FALLBACK_TLE[43700]
    sat = Satellite(name, l1, l2)
    assert sat.is_geo
    p = sat.next_pass(sat.epoch_unix)
    assert p is not None and p.los is None
    lk = sat.look(sat.epoch_unix)
    # QO-100 at 25.9 E seen from Bucharest: almost due south, about 38 deg
    assert 175 < lk.az < 185
    assert 35 < lk.el < 41
