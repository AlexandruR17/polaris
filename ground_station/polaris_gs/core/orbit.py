"""SGP4 propagation, look angles and pass prediction.

Same algorithm as firmware/lib/polaris_core/orbit.cpp:
Vallado SGP4 (WGS72, improved mode) -> TEME -> ECEF (GMST rotation,
no polar motion) -> topocentric ENU of the station (WGS84).
"""
import math
from dataclasses import dataclass
from typing import Optional

from sgp4.api import WGS72, Satrec

from . import config as C

D2R = math.pi / 180.0
R2D = 180.0 / math.pi
WGS84_A = 6378.137
WGS84_F = 1.0 / 298.257223563
UNIX_JD0 = 2440587.5


def unix_to_jd(t):
    return t / 86400.0 + UNIX_JD0


def gmst_rad(jd_ut1):
    """IAU-82 GMST, same as Vallado gstime()."""
    tut1 = (jd_ut1 - 2451545.0) / 36525.0
    temp = (-6.2e-6 * tut1 * tut1 * tut1 + 0.093104 * tut1 * tut1
            + (876600.0 * 3600.0 + 8640184.812866) * tut1 + 67310.54841)
    temp = math.fmod(temp * D2R / 240.0, 2.0 * math.pi)
    if temp < 0.0:
        temp += 2.0 * math.pi
    return temp


def site_ecef(lat_deg, lon_deg, alt_m):
    lat, lon = lat_deg * D2R, lon_deg * D2R
    e2 = WGS84_F * (2.0 - WGS84_F)
    n = WGS84_A / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
    h = alt_m / 1000.0
    return ((n + h) * math.cos(lat) * math.cos(lon),
            (n + h) * math.cos(lat) * math.sin(lon),
            (n * (1.0 - e2) + h) * math.sin(lat))


def teme_to_ecef(r, jd):
    g = gmst_rad(jd)
    c, s = math.cos(g), math.sin(g)
    return (c * r[0] + s * r[1], -s * r[0] + c * r[1], r[2])


def ecef_to_enu(d, lat_deg, lon_deg):
    lat, lon = lat_deg * D2R, lon_deg * D2R
    sl, cl = math.sin(lat), math.cos(lat)
    so, co = math.sin(lon), math.cos(lon)
    e = -so * d[0] + co * d[1]
    n = -sl * co * d[0] - sl * so * d[1] + cl * d[2]
    u = cl * co * d[0] + cl * so * d[1] + sl * d[2]
    return e, n, u


def ecef_to_geodetic(r):
    """Iterative geodetic latitude, used for the ground track."""
    x, y, z = r
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    e2 = WGS84_F * (2.0 - WGS84_F)
    lat = math.atan2(z, p * (1 - e2))
    h = 0.0
    for _ in range(5):
        n = WGS84_A / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1 - e2 * n / (n + h)))
    return lat * R2D, lon * R2D, h


@dataclass
class Look:
    az: float
    el: float
    range_km: float
    r_ecef: tuple


@dataclass
class Pass:
    aos: float
    los: Optional[float]   # None: never sets (geostationary)
    tmax: float
    max_el: float
    aos_az: float
    los_az: Optional[float]


class Satellite:
    def __init__(self, name, line1, line2, lat=C.STATION_LAT_DEG, lon=C.STATION_LON_DEG,
                 alt_m=C.STATION_ALT_M):
        self.name = name
        self.line1 = line1.strip()
        self.line2 = line2.strip()
        self.satrec = Satrec.twoline2rv(self.line1, self.line2, WGS72)
        self.catnr = self.satrec.satnum
        self.epoch_unix = ((self.satrec.jdsatepoch - UNIX_JD0) + self.satrec.jdsatepochF) * 86400.0
        self.lat, self.lon, self.alt_m = lat, lon, alt_m
        self.site = site_ecef(lat, lon, alt_m)
        self.mean_motion_rev_day = self.satrec.no_kozai * 1440.0 / (2.0 * math.pi)

    @property
    def is_geo(self):
        return abs(self.mean_motion_rev_day - 1.0027) < 0.05

    def age_days(self, t_unix):
        return (t_unix - self.epoch_unix) / 86400.0

    def teme(self, t_unix):
        tsince = (t_unix - self.epoch_unix) / 60.0
        err, r, v = self.satrec.sgp4_tsince(tsince)
        if err != 0:
            raise RuntimeError(f"SGP4 error {err}")
        return r, v

    def look(self, t_unix):
        r, _ = self.teme(t_unix)
        rec = teme_to_ecef(r, unix_to_jd(t_unix))
        d = (rec[0] - self.site[0], rec[1] - self.site[1], rec[2] - self.site[2])
        e, n, u = ecef_to_enu(d, self.lat, self.lon)
        rng = math.sqrt(e * e + n * n + u * u)
        az = math.atan2(e, n) * R2D
        if az < 0:
            az += 360.0
        el = math.asin(u / rng) * R2D
        return Look(az, el, rng, rec)

    def elevation(self, t):
        return self.look(t).el

    # ---- pass prediction, mirrored in orbit.cpp ----
    def _bisect(self, t_below, t_above, mask):
        """Crossing between a time below the mask and one above it."""
        for _ in range(40):
            if abs(t_above - t_below) < 0.5:
                break
            m = 0.5 * (t_below + t_above)
            if self.elevation(m) > mask:
                t_above = m
            else:
                t_below = m
        return t_above

    def _max_el(self, a, b):
        g = 0.6180339887498949
        x1 = b - g * (b - a)
        x2 = a + g * (b - a)
        f1, f2 = self.elevation(x1), self.elevation(x2)
        for _ in range(40):
            if b - a < 1.0:
                break
            if f1 < f2:
                a, x1, f1 = x1, x2, f2
                x2 = a + g * (b - a)
                f2 = self.elevation(x2)
            else:
                b, x2, f2 = x2, x1, f1
                x1 = b - g * (b - a)
                f1 = self.elevation(x1)
        t = 0.5 * (a + b)
        return t, self.elevation(t)

    def _find_set(self, t0, horizon_s, mask):
        t = t0
        while t < t0 + horizon_s:
            t2 = t + 20.0
            if self.elevation(t2) <= mask:
                # t is above, t2 is below
                lo, hi = t2, t
                for _ in range(40):
                    if abs(lo - hi) < 0.5:
                        break
                    m = 0.5 * (lo + hi)
                    if self.elevation(m) > mask:
                        hi = m
                    else:
                        lo = m
                return hi
            t = t2
        return None

    def next_pass(self, t0, horizon_h=C.PASS_SEARCH_H, mask=C.MASK_EL_DEG):
        s = PassSearch(self, t0, horizon_h, mask)
        while not s.step(1 << 30):
            pass
        return s.result

    def passes(self, t0, count=5, horizon_h=48.0):
        out = []
        t = t0
        end = t0 + horizon_h * 3600.0
        while len(out) < count and t < end:
            p = self.next_pass(t, horizon_h=(end - t) / 3600.0)
            if p is None:
                break
            out.append(p)
            if p.los is None:
                break
            t = p.los + 60.0
        return out


class PassSearch:
    """next_pass split into small steps, so a slow CPU never blocks its control
    loop: step(budget) evaluates at most `budget` coarse samples; the final
    refinement (AOS, LOS, maximum) runs in the call after the rise is found.
    Same algorithm and budget accounting as PassSearch in pc_orbit.cpp."""

    def __init__(self, sat, t0, horizon_h=C.PASS_SEARCH_H, mask=C.MASK_EL_DEG):
        self.sat, self.t0, self.horizon_s, self.mask = sat, t0, horizon_h * 3600.0, mask
        self.phase = "start"
        self.result = None
        self.t = self.prev = self.aos = 0.0

    @property
    def busy(self):
        return self.phase != "done"

    def cancel(self):
        self.phase = "done"

    def step(self, budget):
        if self.phase == "done":
            return True
        sat, mask, t0 = self.sat, self.mask, self.t0
        if self.phase == "refine":
            aos = self.aos
            los = sat._find_set(max(aos, t0), self.horizon_s, mask)
            if los is None:
                self.result = Pass(aos, None, t0, sat.elevation(t0), sat.look(aos).az, None)
            else:
                tmax, max_el = sat._max_el(aos, los)
                self.result = Pass(aos, los, tmax, max_el, sat.look(aos).az, sat.look(los).az)
            self.phase = "done"
            return True
        if self.phase == "start":
            el0 = sat.elevation(t0)
            budget -= 1
            if sat.is_geo:
                # geostationary: visible all the time or never, no search needed
                if el0 > mask:
                    self.result = Pass(t0, None, t0, el0, sat.look(t0).az, None)
                self.phase = "done"
                return True
            self.t, self.prev = t0, el0
            self.phase = "back" if el0 > mask else "fwd"
        # pass in progress: walk back to AOS (max 30 min)
        while self.phase == "back" and budget > 0:
            if self.t <= t0 - 1800.0:
                self.aos, self.phase = self.t, "refine"
                break
            t2 = self.t - 20.0
            budget -= 1
            if sat.elevation(t2) <= mask:
                self.aos, self.phase = sat._bisect(t2, self.t, mask), "refine"
                break
            self.t = t2
        while self.phase == "fwd" and budget > 0:
            if self.t >= t0 + self.horizon_s:
                self.phase = "done"
                return True
            t2 = self.t + (60.0 if self.prev < -10.0 else 20.0)
            e2 = sat.elevation(t2)
            budget -= 1
            if e2 > mask:
                self.aos, self.phase = sat._bisect(self.t, t2, mask), "refine"
                break
            self.t, self.prev = t2, e2
        return False


def parse_tle_text(text):
    """Return (name, line1, line2) from a 2 or 3 line TLE block."""
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()]
    l1 = next(i for i, ln in enumerate(lines) if ln.startswith("1 "))
    name = lines[l1 - 1].strip() if l1 > 0 else "SAT"
    return name, lines[l1], lines[l1 + 1]


def tle_checksum_ok(line):
    if len(line) < 69:
        return False
    s = 0
    for ch in line[:68]:
        if ch.isdigit():
            s += int(ch)
        elif ch == "-":
            s += 1
    return s % 10 == int(line[68])
