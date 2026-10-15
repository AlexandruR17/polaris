"""Polar sky plot: zenith in the centre, horizon on the rim, north up, east right."""
import math

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui

from ..core import config as C
from . import theme as T


def polar(az, el):
    r = 90.0 - np.clip(el, -5, 90)
    a = np.radians(az)
    return r * np.sin(a), r * np.cos(a)


class SkyPlot(pg.PlotWidget):
    def __init__(self):
        super().__init__(background=T.BG)
        self.setAspectLocked(True)
        self.hideAxis("left")
        self.hideAxis("bottom")
        self.setMouseEnabled(False, False)
        self.setMenuEnabled(False)
        self.setRange(xRange=(-104, 104), yRange=(-104, 104), padding=0)
        grid = pg.mkPen(T.GRID, width=1)
        for el in (0, 30, 60):
            r = 90 - el
            t = np.linspace(0, 2 * math.pi, 181)
            self.plot(r * np.sin(t), r * np.cos(t), pen=pg.mkPen(T.BORDER if el == 0 else T.GRID, width=1.5 if el == 0 else 1))
            if el:
                lab = pg.TextItem(f"{el}°", color=T.MUTED, anchor=(0, 1))
                lab.setPos(2, r)
                self.addItem(lab)
        mask_r = 90 - C.MASK_EL_DEG
        t = np.linspace(0, 2 * math.pi, 181)
        self.plot(mask_r * np.sin(t), mask_r * np.cos(t), pen=pg.mkPen(T.MUTED, width=1, style=QtCore.Qt.PenStyle.DashLine))
        for az in range(0, 360, 30):
            a = math.radians(az)
            self.plot([0, 90 * math.sin(a)], [0, 90 * math.cos(a)], pen=grid)
        for name, az in (("N", 0), ("E", 90), ("S", 180), ("V", 270)):
            a = math.radians(az)
            lab = pg.TextItem(name, color=T.TEXT_2, anchor=(0.5, 0.5))
            lab.setFont(QtGui.QFont(T.FONT, 12, QtGui.QFont.Weight.Bold))
            lab.setPos(98 * math.sin(a), 98 * math.cos(a))
            self.addItem(lab)
        self.track = self.plot([], [], pen=pg.mkPen(T.ACCENT, width=2))
        self.past = self.plot([], [], pen=pg.mkPen(T.MUTED, width=2))
        self.err_line = self.plot([], [], pen=pg.mkPen(T.TEXT_2, width=1.5, style=QtCore.Qt.PenStyle.DotLine))
        self.sat = pg.ScatterPlotItem(size=16, brush=pg.mkBrush(T.ACCENT), pen=pg.mkPen(T.BG, width=2))
        self.ant = pg.ScatterPlotItem(size=20, symbol="+", brush=pg.mkBrush(T.SECOND), pen=pg.mkPen(T.SECOND, width=3))
        self.addItem(self.sat)
        self.addItem(self.ant)
        self.aos_lab = pg.TextItem("", color=T.TEXT_2, anchor=(0.5, 1.2))
        self.addItem(self.aos_lab)
        # legend: series identity is not colour alone
        legend = pg.LegendItem(offset=(6, 6), labelTextColor=T.TEXT_2, labelTextSize="10pt")
        legend.setParentItem(self.getPlotItem())
        legend.addItem(self.sat, "satelit")
        legend.addItem(self.ant, "antenă (direcția reală)")
        legend.addItem(self.track, "pasaj")

    def set_track(self, az, el):
        if len(az):
            x, y = polar(np.array(az), np.array(el))
            self.track.setData(x, y)
            self.aos_lab.setText("AOS")
            self.aos_lab.setPos(x[0], y[0])
        else:
            self.track.setData([], [])
            self.aos_lab.setText("")

    def set_positions(self, sat_az, sat_el, ant_az, ant_el):
        sx, sy = polar(np.array([sat_az]), np.array([sat_el]))
        ax, ay = polar(np.array([ant_az]), np.array([ant_el]))
        self.sat.setData(sx, sy)
        self.ant.setData(ax, ay)
        if sat_el > -5:
            self.err_line.setData([sx[0], ax[0]], [sy[0], ay[0]])
        else:
            self.err_line.setData([], [])
