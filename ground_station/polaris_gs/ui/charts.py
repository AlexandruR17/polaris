"""Time charts: one measure per chart (no dual axes), last few minutes."""
import pyqtgraph as pg
from PySide6 import QtGui

from . import theme as T


def styled_plot(title, unit):
    p = pg.PlotWidget(background=T.BG)
    p.setMenuEnabled(False)
    p.showGrid(x=True, y=True, alpha=0.18)
    for ax in ("left", "bottom"):
        a = p.getAxis(ax)
        a.setPen(pg.mkPen(T.BORDER))
        a.setTextPen(pg.mkPen(T.TEXT_2))
        a.setStyle(tickFont=QtGui.QFont(T.FONT, 9))
    p.setLabel("left", unit, color=T.TEXT_2)
    p.setTitle(f"<span style='color:{T.TEXT_2};font-size:11pt'>{title}</span>")
    p.setXRange(-120, 0, padding=0)
    p.setMouseEnabled(x=False, y=False)
    return p


class Charts:
    def __init__(self):
        self.err = styled_plot("Eroare de pointare", "grade")
        self.err_curve = self.err.plot([], [], pen=pg.mkPen(T.ACCENT, width=2))
        self.err.addLine(y=1.0, pen=pg.mkPen(T.MUTED, width=1, style=pg.QtCore.Qt.PenStyle.DashLine))
        self.speed = styled_plot("Viteza axelor", "°/s")
        lg = self.speed.addLegend(offset=(8, 4), labelTextColor=T.TEXT_2)
        self.az_curve = self.speed.plot([], [], pen=pg.mkPen(T.AZ_COLOR, width=2), name="azimut")
        self.el_curve = self.speed.plot([], [], pen=pg.mkPen(T.EL_COLOR, width=2), name="elevație")
        self.att = styled_plot("Înclinarea vehiculului", "grade")
        self.att.addLegend(offset=(8, 4), labelTextColor=T.TEXT_2)
        self.roll_curve = self.att.plot([], [], pen=pg.mkPen(T.ACCENT, width=2), name="ruliu (roll)")
        self.pitch_curve = self.att.plot([], [], pen=pg.mkPen(T.SECOND, width=2), name="tangaj (pitch)")
        self.widgets = (self.err, self.speed, self.att)
        _ = lg

    def update(self, store):
        x, y = store.series("err_deg")
        self.err_curve.setData(x, y)
        tracking = [d for d in list(store.hist)[-1200:] if d["mode"] in ("TRACK", "ACQUIRE")]
        top = max([d["err_deg"] for d in tracking], default=2.0)
        self.err.setYRange(0, max(2.0, min(top * 1.15, 30.0)), padding=0)
        self.az_curve.setData(*store.series("_az_rate"))
        self.el_curve.setData(*store.series("_el_rate"))
        self.roll_curve.setData(*store.series("roll"))
        self.pitch_curve.setData(*store.series("pitch"))
