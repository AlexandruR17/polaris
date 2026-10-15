"""Independent check of the controller's satellite position with skyfield."""
import datetime as dt

from skyfield.api import EarthSatellite, load, wgs84

from .core import config as C
from .core import geometry as G
from .core.tle_data import FALLBACK_TLE


class CrossCheck:
    def __init__(self):
        self.ts = load.timescale(builtin=True)
        self.site = wgs84.latlon(C.STATION_LAT_DEG, C.STATION_LON_DEG, elevation_m=C.STATION_ALT_M)
        self.tles = dict(FALLBACK_TLE)
        self._sats = {}

    def set_tle(self, catnr, name, l1, l2):
        self.tles[catnr] = (name, l1, l2)
        self._sats.pop(catnr, None)

    def azel(self, catnr, t_unix):
        if catnr not in self.tles:
            return None
        if catnr not in self._sats:
            name, l1, l2 = self.tles[catnr]
            self._sats[catnr] = EarthSatellite(l1, l2, name, self.ts)
        t = self.ts.from_datetime(dt.datetime.fromtimestamp(t_unix, dt.timezone.utc))
        alt, az, dist = (self._sats[catnr] - self.site).at(t).altaz()
        return az.degrees, alt.degrees, dist.km

    def difference(self, telem):
        """Angle between controller and skyfield directions, degrees."""
        r = self.azel(telem["sat"], telem["t_utc_unix"])
        if r is None:
            return None
        az, el, _ = r
        return G.angle_between(G.azel_to_enu(az, el), G.azel_to_enu(telem["sat_az"], telem["sat_el"]))
