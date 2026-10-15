"""3D globe in the Earth-fixed frame: coastlines, orbit, ground track,
station visibility cone and the live satellite position. 1 unit = Earth radius."""
import json
import math
import pathlib

import numpy as np
import pyqtgraph.opengl as gl
from PySide6 import QtGui

from ..core import config as C
from ..core.orbit import WGS84_A, ecef_to_geodetic, site_ecef
from . import theme as T

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "assets"


def rgba(hex_color, a=1.0):
    c = QtGui.QColor(hex_color)
    return (c.redF(), c.greenF(), c.blueF(), a)


def ll_to_xyz(lat, lon, r=1.0):
    lat, lon = np.radians(lat), np.radians(lon)
    return np.stack([r * np.cos(lat) * np.cos(lon), r * np.cos(lat) * np.sin(lon), r * np.sin(lat)], -1)


class GlobeView(gl.GLViewWidget):
    def __init__(self):
        super().__init__()
        self.setBackgroundColor(T.BG)
        self.setCameraPosition(distance=4.2, elevation=32, azimuth=C.STATION_LON_DEG + 15)
        self.opts["fov"] = 40
        md = gl.MeshData.sphere(rows=48, cols=96, radius=0.995)
        self.addItem(gl.GLMeshItem(meshdata=md, smooth=True, color=rgba("#132544"), shader="shaded",
                                   glOptions="opaque"))
        # graticule every 30 deg
        for lat in range(-60, 90, 30):
            lon = np.linspace(-180, 180, 181)
            self._line(ll_to_xyz(np.full_like(lon, lat), lon, 1.001), "#22355a", 1)
        for lon in range(-180, 180, 30):
            lat = np.linspace(-90, 90, 91)
            self._line(ll_to_xyz(lat, np.full_like(lat, lon), 1.001), "#22355a", 1)
        coast = json.loads((ASSETS / "coastline_110m.json").read_text())["lines"]
        for ln in coast:
            a = np.array(ln)
            self._line(ll_to_xyz(a[:, 1], a[:, 0], 1.002), "#6f87b3", 1.2)
        st = np.array(site_ecef(C.STATION_LAT_DEG, C.STATION_LON_DEG, C.STATION_ALT_M)) / WGS84_A
        self.station = st
        self.addItem(gl.GLScatterPlotItem(pos=st[None, :] * 1.004, size=11, color=rgba(T.ACCENT),
                                          pxMode=True))
        self.orbit = self._line(np.zeros((2, 3)), "#c9d6ee", 1.4, 0.75)
        self.track = self._line(np.zeros((2, 3)), T.ACCENT, 2.0)
        self.footprint = self._line(np.zeros((2, 3)), T.SECOND, 2.0)
        self.cone = gl.GLLinePlotItem(pos=np.zeros((2, 3)), color=rgba(T.SECOND, 0.45), width=1,
                                      mode="lines", antialias=True)
        self.addItem(self.cone)
        self.sat = gl.GLScatterPlotItem(pos=np.zeros((1, 3)), size=14, color=rgba("#ffffff"), pxMode=True)
        self.addItem(self.sat)
        self.link = gl.GLLinePlotItem(pos=np.zeros((2, 3)), color=rgba(T.ACCENT, 0.9), width=2,
                                      antialias=True)
        self.addItem(self.link)

    def _line(self, pts, color, width, alpha=1.0):
        item = gl.GLLinePlotItem(pos=pts, color=rgba(color, alpha), width=width, antialias=True)
        self.addItem(item)
        return item

    def update_orbit(self, sat, t):
        """Orbit and ground track over one period around t (Earth-fixed frame)."""
        if sat.is_geo:
            period = 86164.0
        else:
            period = 86400.0 / sat.mean_motion_rev_day
        ts = np.linspace(t - 0.5 * period, t + 0.5 * period, 361)
        pos, sub = [], []
        for tt in ts:
            r = np.array(sat.look(tt).r_ecef) / WGS84_A
            pos.append(r)
            sub.append(r / np.linalg.norm(r) * 1.003)
        self.orbit.setData(pos=np.array(pos))
        self.track.setData(pos=np.array(sub))

    def update_satellite(self, sat, t, sat_el):
        lk = sat.look(t)
        r = np.array(lk.r_ecef) / WGS84_A
        self.sat.setData(pos=r[None, :], color=rgba("#ffffff" if sat_el <= C.MASK_EL_DEG else T.ACCENT))
        if sat_el > C.MASK_EL_DEG:
            self.link.setData(pos=np.array([self.station * 1.004, r]))
        else:
            self.link.setData(pos=np.zeros((2, 3)))
        # visibility footprint for the current altitude and the 5 deg mask
        _, _, h = ecef_to_geodetic(lk.r_ecef)
        e = math.radians(C.MASK_EL_DEG)
        lam = math.acos(WGS84_A / (WGS84_A + h) * math.cos(e)) - e
        n = self.station / np.linalg.norm(self.station)
        u = np.cross(n, [0, 0, 1.0])
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        ang = np.linspace(0, 2 * math.pi, 121)
        circle = (np.cos(lam) * n[None, :] + np.sin(lam) * (np.cos(ang)[:, None] * u + np.sin(ang)[:, None] * v))
        self.footprint.setData(pos=circle * 1.004)
        k = (WGS84_A + h) / WGS84_A
        edges = []
        for a in ang[::10]:
            p = (np.cos(lam) * n + np.sin(lam) * (math.cos(a) * u + math.sin(a) * v)) * k
            edges += [self.station * 1.004, p]
        self.cone.setData(pos=np.array(edges))
