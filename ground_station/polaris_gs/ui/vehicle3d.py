"""3D vehicle with the antenna pedestal, driven by roll/pitch/yaw and the
two axis angles. World frame ENU (x east, y north, z up), vehicle FLU."""
import math

import numpy as np
import pyqtgraph.opengl as gl
from PySide6 import QtGui

from ..core import geometry as G
from . import theme as T
from .globe import rgba


def box(sx, sy, sz, cx=0.0, cy=0.0, cz=0.0):
    v = np.array([[x, y, z] for x in (-sx / 2, sx / 2) for y in (-sy / 2, sy / 2) for z in (-sz / 2, sz / 2)])
    v += [cx, cy, cz]
    f = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                  [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    return gl.MeshData(vertexes=v, faces=f)


def cylinder_z(r, h, cz=0.0, n=32):
    md = gl.MeshData.cylinder(rows=1, cols=n, radius=[r, r], length=h)
    v = md.vertexes()
    v[:, 2] += cz - h / 2
    caps = []
    verts = list(v)
    base = len(verts)
    verts.append([0, 0, cz - h / 2])
    verts.append([0, 0, cz + h / 2])
    for i in range(n):
        j = (i + 1) % n
        caps.append([base, i, j])
        caps.append([base + 1, n + j, n + i])
    faces = np.vstack([md.faces(), np.array(caps)])
    return gl.MeshData(vertexes=np.array(verts), faces=faces)


def dish(r=0.9, depth=0.28, n=40, rings=8):
    """Paraboloid opening along +x (boresight)."""
    verts, faces = [[0, 0, 0]], []
    for i in range(1, rings + 1):
        rr = r * i / rings
        for k in range(n):
            a = 2 * math.pi * k / n
            verts.append([depth * (rr / r) ** 2, rr * math.cos(a), rr * math.sin(a)])
    for k in range(n):
        faces.append([0, 1 + k, 1 + (k + 1) % n])
    for i in range(1, rings):
        b0, b1 = 1 + (i - 1) * n, 1 + i * n
        for k in range(n):
            k2 = (k + 1) % n
            faces += [[b0 + k, b1 + k, b1 + k2], [b0 + k, b1 + k2, b0 + k2]]
    return gl.MeshData(vertexes=np.array(verts, float), faces=np.array(faces))


def mat(R, t=(0, 0, 0)):
    """4x4 transform from a rotation matrix and a translation."""
    vals = []
    for i in range(3):
        vals += [float(R[i, 0]), float(R[i, 1]), float(R[i, 2]), float(t[i])]
    return QtGui.QMatrix4x4(*vals, 0.0, 0.0, 0.0, 1.0)


class VehicleView(gl.GLViewWidget):
    def __init__(self):
        super().__init__()
        self.setBackgroundColor(T.BG)
        self.setCameraPosition(distance=10, elevation=20, azimuth=-60)
        self.opts["center"] = QtGui.QVector3D(0, 0, 2.0)
        grid = gl.GLGridItem()
        grid.setSize(16, 16)
        grid.setSpacing(1, 1)
        grid.setColor(rgba("#2a3b5e"))
        self.addItem(grid)
        # compass marks on the ground
        self.addItem(gl.GLLinePlotItem(pos=np.array([[0, 0, 0.01], [0, 7, 0.01]]), color=rgba(T.MUTED), width=2))
        self.parts = []

        def add(md, color, edges=True):
            # flat colour plus dark edges: readable on a projector, no lighting needed
            it = gl.GLMeshItem(meshdata=md, smooth=False, color=rgba(color), shader=None,
                               drawEdges=edges, edgeColor=rgba("#0b1220", 0.6), glOptions="opaque")
            self.addItem(it)
            return it

        # vehicle body frame items: (item, fixed transform in body frame)
        self.body_items = [
            (add(box(4.6, 2.0, 0.9, cz=0.85), "#6b7fa6"), None),
            (add(box(1.6, 1.9, 0.7, cx=1.4, cz=1.6), "#8aa0c8"), None),   # cab, forward
        ]
        for wx in (-1.5, 1.5):
            for wy in (-1.05, 1.05):
                w = add(cylinder_z(0.45, 0.35, cz=0), "#2a3245")
                self.body_items.append((w, ("wheel", wx, wy)))
        self.base = add(cylinder_z(0.45, 0.35, cz=1.5), "#b8c4dc")
        self.turret = add(box(0.5, 0.5, 0.7, cz=0.35), T.SECOND)
        self.cradle = add(box(0.2, 1.2, 0.2), "#9fb0cc")
        self.dish = add(dish(), "#d8e1f0", edges=False)
        self.bore = gl.GLLinePlotItem(pos=np.zeros((2, 3)), color=rgba(T.SECOND), width=3, antialias=True)
        self.addItem(self.bore)
        self.target = gl.GLLinePlotItem(pos=np.zeros((2, 3)), color=rgba(T.ACCENT), width=3, antialias=True)
        self.addItem(self.target)
        self.set_state(0, 0, 90, 0, 90, 0, 90)

    def set_state(self, roll, pitch, yaw, ped_az, ped_el, sat_az, sat_el):
        R = G.attitude_matrix(roll, pitch, yaw)
        for it, extra in self.body_items:
            if extra is None:
                it.setTransform(mat(R))
            else:
                _, wx, wy = extra
                Rw = R @ G.rot_x(math.pi / 2)
                it.setTransform(mat(Rw, R @ np.array([wx, wy, 0.45])))
        self.base.setTransform(mat(R))
        # turret: pedestal azimuth, clockwise from forward = rotation about -z
        Ra = R @ G.rot_z(math.radians(-ped_az))
        top = R @ np.array([0, 0, 1.68])
        self.turret.setTransform(mat(Ra, top))
        Re = Ra @ G.rot_y(math.radians(-ped_el))
        hinge = top + Ra @ np.array([0, 0, 0.9])
        self.cradle.setTransform(mat(Ra, hinge))
        self.dish.setTransform(mat(Re, hinge + Re @ np.array([0.05, 0, 0])))
        b = Re @ np.array([1.0, 0, 0])
        self.bore.setData(pos=np.array([hinge, hinge + 4.5 * b]))
        s = G.azel_to_enu(sat_az, sat_el)
        if sat_el > -5:
            self.target.setData(pos=np.array([hinge, hinge + 6.0 * s]))
        else:
            self.target.setData(pos=np.zeros((2, 3)))
