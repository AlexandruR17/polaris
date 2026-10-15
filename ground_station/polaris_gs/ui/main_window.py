"""POLARIS Ground Station main window."""
import datetime as dt
import math
import time

import qtawesome as qta
from PySide6 import QtCore, QtGui, QtWidgets

from ..core import config as C
from ..core import protocol as P
from ..core.orbit import Satellite
from ..crosscheck import CrossCheck
from ..link import SerialLink, SimLink
from ..store import ResultsDB, TelemetryStore
from ..vehicle import MODES as VEH_MODES
from ..vehicle import VehicleMotion
from . import theme as T
from .charts import Charts
from .globe import GlobeView
from .skyplot import SkyPlot
from .vehicle3d import VehicleView

SAT_NAMES = {25544: "ISS", 33591: "NOAA 19", 28654: "NOAA 18", 43700: "QO-100 (geostaționar)"}

EVENT_RO = {
    "BOOT": "Pornire firmware", "AOS": "AOS: satelitul a răsărit", "LOS": "LOS: satelitul a apus",
    "HOME_OK": "Homing reușit", "ESTOP": "OPRIRE DE URGENȚĂ", "FAULT": "DEFECT", "MODE": "Stare",
    "TLE_OK": "TLE descărcat", "TLE_FALLBACK": "TLE de rezervă (vechi)", "KEYHOLE": "Keyhole",
    "RATE_LIMIT": "Limită de viteză", "WRAP": "Derulare cablu", "PASS": "Pasaj calculat",
    "ACK": "Confirmare", "CMD": "Comandă", "ERR": "Eroare comandă", "INFO": "Info",
}


def icon(name, color=T.TEXT):
    return qta.icon(f"mdi6.{name}", color=color)


def panel(title, icon_name, widget, stretch=True):
    f = QtWidgets.QFrame()
    f.setObjectName("panel")
    lay = QtWidgets.QVBoxLayout(f)
    lay.setContentsMargins(10, 8, 10, 10)
    lay.setSpacing(6)
    head = QtWidgets.QHBoxLayout()
    ic = QtWidgets.QLabel()
    ic.setPixmap(icon(icon_name, T.ACCENT).pixmap(18, 18))
    lab = QtWidgets.QLabel(title.upper())
    lab.setObjectName("panelTitle")
    head.addWidget(ic)
    head.addWidget(lab)
    head.addStretch(1)
    lay.addLayout(head)
    if isinstance(widget, QtWidgets.QLayout):
        lay.addLayout(widget, 1 if stretch else 0)
    else:
        lay.addWidget(widget, 1 if stretch else 0)
    return f


class Chip(QtWidgets.QFrame):
    """Header value: small caption over a large value."""

    def __init__(self, caption, icon_name):
        super().__init__()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(12, 4, 12, 4)
        self.ic = QtWidgets.QLabel()
        self.icon_name = icon_name
        self.ic.setPixmap(icon(icon_name, T.TEXT_2).pixmap(26, 26))
        lay.addWidget(self.ic)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(0)
        cap = QtWidgets.QLabel(caption)
        cap.setObjectName("small")
        self.val = QtWidgets.QLabel("—")
        self.val.setObjectName("bigValue")
        col.addWidget(cap)
        col.addWidget(self.val)
        lay.addLayout(col)

    def set(self, text, color=T.TEXT, icon_name=None):
        self.val.setText(text)
        self.val.setStyleSheet(f"color:{color}")
        self.ic.setPixmap(icon(icon_name or self.icon_name, color if color != T.TEXT else T.TEXT_2).pixmap(26, 26))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, link_spec="sim", db_path=None, online_tle=False):
        super().__init__()
        self.setWindowTitle("POLARIS Ground Station")
        self.setWindowIcon(icon("satellite-uplink", T.ACCENT))
        self.store = TelemetryStore()
        self.db = ResultsDB(db_path) if db_path else None
        self.xcheck = CrossCheck()
        self.online_tle = online_tle
        self.vehicle = VehicleMotion("stationary")
        self.veh_t0 = time.monotonic()
        self.link = None
        self.sats = {}
        self.sat_id = C.DEFAULT_SAT
        self.last_orbit_update = 0.0
        self.last_pass_update = 0.0
        self.xcheck_diff = None
        self._build()
        self.connect_link(link_spec)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(100)
        self.veh_timer = QtCore.QTimer(self)
        self.veh_timer.timeout.connect(self.send_vehicle)
        self.veh_timer.start(50)

    # ------------------------------------------------------------ layout
    def _build(self):
        root = QtWidgets.QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        grid = QtWidgets.QGridLayout(root)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(10)

        # header
        head = QtWidgets.QFrame()
        head.setObjectName("panel")
        hl = QtWidgets.QHBoxLayout(head)
        hl.setContentsMargins(14, 6, 14, 6)
        logo = QtWidgets.QLabel()
        logo.setPixmap(icon("satellite-uplink", T.ACCENT).pixmap(40, 40))
        title = QtWidgets.QLabel("POLARIS <span style='color:%s'>Ground Station</span>" % T.ACCENT)
        title.setStyleSheet("font-size:21px;font-weight:800;letter-spacing:1px")
        sub = QtWidgets.QLabel("SAT-1 · Politehnica București 44.4386°N 26.0494°E")
        sub.setObjectName("small")
        tcol = QtWidgets.QVBoxLayout()
        tcol.setSpacing(0)
        tcol.addWidget(title)
        tcol.addWidget(sub)
        hl.addWidget(logo)
        hl.addLayout(tcol)
        hl.addSpacing(20)
        self.chip_state = Chip("Stare", "radar")
        self.chip_utc = Chip("Ora UTC", "clock-outline")
        self.chip_sat = Chip("Satelit · az / el", "satellite-variant")
        self.chip_err = Chip("Eroare pointare", "crosshairs-gps")
        self.chip_tle = Chip("TLE", "database")
        self.chip_x = Chip("Verificare skyfield", "check-decagram")
        for c in (self.chip_state, self.chip_utc, self.chip_sat, self.chip_err, self.chip_tle, self.chip_x):
            hl.addWidget(c)
        hl.addStretch(1)
        grid.addWidget(head, 0, 0, 1, 4)

        grid.addWidget(self._controls(), 1, 0, 2, 1)
        self.globe = GlobeView()
        grid.addWidget(panel("Glob · orbită, urmă la sol, con de vizibilitate", "earth", self.globe), 1, 1)
        self.sky = SkyPlot()
        grid.addWidget(panel("Harta cerului · pasaj, satelit, antenă", "radar", self.sky), 1, 2)
        self.veh3d = VehicleView()
        grid.addWidget(panel("Vehicul și piedestal (live)", "car-side", self.veh3d), 2, 1)
        self.charts = Charts()
        ch = QtWidgets.QVBoxLayout()
        ch.setSpacing(4)
        for w in self.charts.widgets:
            ch.addWidget(w)
        grid.addWidget(panel("Grafice · ultimele 2 minute", "chart-line", ch), 2, 2)

        right = QtWidgets.QVBoxLayout()
        self.passes = QtWidgets.QTableWidget(0, 6)
        self.passes.setHorizontalHeaderLabels(["AOS", "LOS", "Max el", "Durată", "Az", "Δ sky"])
        self.passes.verticalHeader().setVisible(False)
        self.passes.setAlternatingRowColors(True)
        self.passes.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.passes.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.passes.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        right.addWidget(panel("Următoarele pasaje", "table", self.passes))
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(400)
        self.log.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
        right.addWidget(panel("Jurnal de evenimente", "text-box-outline", self.log))
        rw = QtWidgets.QWidget()
        rw.setLayout(right)
        right.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(rw, 1, 3, 2, 1)

        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 5)
        grid.setColumnStretch(2, 5)
        grid.setColumnStretch(3, 4)
        rw.setMinimumWidth(380)
        rw.setMaximumWidth(460)
        head.setMaximumWidth(1900)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 1)

    def _controls(self):
        w = QtWidgets.QWidget()
        w.setFixedWidth(290)
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # link
        ll = QtWidgets.QVBoxLayout()
        self.link_combo = QtWidgets.QComboBox()
        self.link_combo.addItem(icon("robot-industrial"), "Simulare internă", "sim")
        self.link_combo.addItem(icon("lan-connect"), "Wokwi (rfc2217://localhost:4000)", "rfc2217://localhost:4000")
        self.link_combo.addItem(icon("access-point"), "Port serial…", "port")
        self.port_edit = QtWidgets.QLineEdit()
        self.port_edit.setPlaceholderText("COM3 sau /dev/ttyUSB0")
        b = QtWidgets.QPushButton(icon("lan-connect"), " Conectează")
        b.clicked.connect(self._reconnect)
        self.link_label = QtWidgets.QLabel("—")
        self.link_label.setObjectName("small")
        self.link_label.setWordWrap(True)
        for x in (self.link_combo, self.port_edit, b, self.link_label):
            ll.addWidget(x)
        lay.addWidget(panel("Legătură", "lan-connect", ll, False))

        # satellite and mode
        sl = QtWidgets.QVBoxLayout()
        self.sat_combo = QtWidgets.QComboBox()
        for k, v in SAT_NAMES.items():
            self.sat_combo.addItem(icon("satellite-variant"), f"{v}  ·  {k}", k)
        self.sat_combo.activated.connect(lambda _: self.cmd(f"SAT:{self.sat_combo.currentData()}"))
        sl.addWidget(self.sat_combo)
        modes = QtWidgets.QGridLayout()
        self.mode_buttons = {}
        for i, (m, text, ic) in enumerate((("AUTO", "Automat", "satellite-uplink"),
                                          ("DEMO", "Demo", "fast-forward"),
                                          ("MANUAL", "Manual", "hand-back-right"),
                                          ("IDLE", "Repaus", "pause-circle"))):
            btn = QtWidgets.QPushButton(icon(ic), " " + text)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, m=m: self.cmd(f"MODE:{m}"))
            modes.addWidget(btn, i // 2, i % 2)
            self.mode_buttons[m] = btn
        sl.addLayout(modes)
        wl = QtWidgets.QHBoxLayout()
        self.warp_buttons = {}
        lab = QtWidgets.QLabel("Viteză DEMO")
        lab.setObjectName("small")
        wl.addWidget(lab)
        for wv in C.DEMO_WARPS:
            btn = QtWidgets.QPushButton(f"x{wv}")
            btn.setCheckable(True)
            btn.setChecked(wv == C.DEFAULT_DEMO_WARP)
            btn.clicked.connect(lambda _=False, wv=wv: self._set_warp(wv))
            wl.addWidget(btn)
            self.warp_buttons[wv] = btn
        sl.addLayout(wl)
        al = QtWidgets.QHBoxLayout()
        for text, ic, c in (("Home", "home-import-outline", "HOME"), ("Stow", "parking", "STOW"),
                            ("ACK", "check-circle", "ACK")):
            btn = QtWidgets.QPushButton(icon(ic), " " + text)
            btn.clicked.connect(lambda _=False, c=c: self.cmd(c))
            al.addWidget(btn)
        sl.addLayout(al)
        lay.addWidget(panel("Satelit și mod", "satellite-uplink", sl, False))

        # vehicle
        vl = QtWidgets.QVBoxLayout()
        self.veh_combo = QtWidgets.QComboBox()
        for k, v in VEH_MODES.items():
            self.veh_combo.addItem(icon("car-side"), v, k)
        self.veh_combo.currentIndexChanged.connect(self._veh_mode)
        self.veh_send = QtWidgets.QCheckBox("Trimite VEH (înlocuiește MPU)")
        self.veh_send.setChecked(True)
        self.comp = QtWidgets.QCheckBox("Compensare înclinare activă")
        self.comp.setChecked(True)
        self.comp.toggled.connect(lambda on: self.cmd(f"COMP:{1 if on else 0}"))
        for x in (self.veh_combo, self.veh_send, self.comp):
            vl.addWidget(x)
        lay.addWidget(panel("Mișcare vehicul", "car-side", vl, False))

        # manual jog
        jl = QtWidgets.QGridLayout()
        for i, (text, ic, c) in enumerate((("AZ −5°", "arrow-left-bold", "JOG:AZ,-5"),
                                           ("AZ +5°", "arrow-right-bold", "JOG:AZ,5"),
                                           ("EL −5°", "arrow-down-bold", "JOG:EL,-5"),
                                           ("EL +5°", "arrow-up-bold", "JOG:EL,5"))):
            btn = QtWidgets.QPushButton(icon(ic), " " + text)
            btn.clicked.connect(lambda _=False, c=c: self.cmd(c))
            jl.addWidget(btn, i // 2, i % 2)
        lay.addWidget(panel("Reglaj manual", "axis-arrow", jl, False))

        # safety (simulation only: a real E-STOP is a physical button)
        fl = QtWidgets.QVBoxLayout()
        self.estop_btn = QtWidgets.QPushButton(icon("alert-octagon", T.CRITICAL), " E-STOP (simulare)")
        self.estop_btn.setObjectName("danger")
        self.estop_btn.setCheckable(True)
        self.estop_btn.toggled.connect(self._estop)
        self.lim_btn = QtWidgets.QPushButton(icon("alert", T.WARNING), " Injectează limitator AZ")
        self.lim_btn.setCheckable(True)
        self.lim_btn.toggled.connect(lambda on: self.link.set_limit("AZ", on) if isinstance(self.link, SimLink) else None)
        fl.addWidget(self.estop_btn)
        fl.addWidget(self.lim_btn)
        lay.addWidget(panel("Siguranță", "alert-octagon", fl, False))
        lay.addStretch(1)
        return w

    # ------------------------------------------------------------ link
    def connect_link(self, spec):
        if self.link:
            self.link.stop()
        if spec == "sim":
            self.link = SimLink(online_tle=self.online_tle)
        else:
            self.link = SerialLink(spec)
        self.link.line.connect(self.on_line)
        self.link.status.connect(lambda text, ok: self.link_label.setText(("● " if ok else "○ ") + text))
        self.link.start()
        is_sim = isinstance(self.link, SimLink)
        self.estop_btn.setEnabled(is_sim)
        self.lim_btn.setEnabled(is_sim)
        idx = 0 if spec == "sim" else (1 if spec.startswith("rfc2217") else 2)
        self.link_combo.setCurrentIndex(idx)

    def _reconnect(self):
        spec = self.link_combo.currentData()
        if spec == "port":
            spec = self.port_edit.text().strip() or "/dev/ttyUSB0"
        self.store = TelemetryStore()
        self.connect_link(spec)

    def cmd(self, c):
        if self.link:
            self.link.send(c)

    def _set_warp(self, w):
        for k, b in self.warp_buttons.items():
            b.setChecked(k == w)
        self.cmd(f"WARP:{w}")

    def _veh_mode(self):
        self.vehicle.set_mode(self.veh_combo.currentData())
        self.veh_t0 = time.monotonic()

    def _estop(self, on):
        if isinstance(self.link, SimLink):
            self.link.set_estop(on)

    def send_vehicle(self):
        if not self.veh_send.isChecked():
            return
        r, p, y = self.vehicle.attitude(time.monotonic() - self.veh_t0)
        self.cmd(P.format_command("VEH", r, p, y).strip())

    # ------------------------------------------------------------ incoming
    def on_line(self, text):
        parsed = P.parse_line(text)
        if not parsed:
            return
        kind, d = parsed
        if kind == "telemetry":
            self.store.add_telemetry(d)
            if d["sat"] != self.sat_id:
                self.sat_id = d["sat"]
                self.last_orbit_update = self.last_pass_update = 0
            return
        self.store.add_event(d)
        ev = d["ev"]
        if ev == "CMD" and d.get("cmd", "").startswith("VEH"):
            return  # 20 Hz vehicle stream, keep the log readable
        if ev == "LOS" and self.db:
            self.db.save_pass(d, self.link.name, self.veh_combo.currentData())
        if ev in ("PASS", "TLE_OK", "TLE_FALLBACK"):
            self.last_orbit_update = self.last_pass_update = 0
        self._log(d)

    def _log(self, d):
        ev = d["ev"]
        color = {"ESTOP": T.CRITICAL, "FAULT": T.CRITICAL, "ERR": T.CRITICAL, "AOS": T.GOOD,
                 "LOS": T.WARNING, "KEYHOLE": T.WARNING, "RATE_LIMIT": T.WARNING,
                 "TLE_FALLBACK": T.WARNING, "HOME_OK": T.GOOD}.get(ev, T.TEXT_2)
        rest = ", ".join(f"{k}={v}" for k, v in d.items() if k not in ("ev", "_wall"))
        if ev == "MODE":
            rest = f"{T.STATE_RO.get(d['from'], d['from'])} → {T.STATE_RO.get(d['to'], d['to'])}"
        t = time.strftime("%H:%M:%S", time.gmtime(d["_wall"]))
        self.log.appendHtml(f"<span style='color:{T.MUTED}'>{t}</span> "
                            f"<b style='color:{color}'>{EVENT_RO.get(ev, ev)}</b> "
                            f"<span style='color:{T.TEXT_2}'>{rest}</span>")

    # ------------------------------------------------------------ periodic refresh
    def _sat(self, catnr):
        name, l1, l2 = self.xcheck.tles[catnr]
        key = (catnr, l1)
        if key not in self.sats:
            self.sats[key] = Satellite(name, l1, l2)
        return self.sats[key]

    def refresh(self):
        d = self.store.last
        if d is None:
            return
        st = d["mode"]
        color = T.STATE_STATUS.get(st, T.TEXT)
        ic = {"ESTOP": "alert-octagon", "FAULT": "alert", "TRACK": "check-circle"}.get(st, "radar")
        label = T.STATE_RO.get(st, st) + (f"  x{d['warp']}" if d.get("warp", 1) > 1 else "")
        self.chip_state.set(label, color, ic)
        self.chip_utc.set(d["t_utc"][11:19])
        name = SAT_NAMES.get(d["sat"], str(d["sat"])).split(" (")[0]
        self.chip_sat.set(f"{name}  {d['sat_az']:.1f}° / {d['sat_el']:.1f}°")
        if st in ("TRACK", "ACQUIRE"):
            e = d["err_deg"]
            self.chip_err.set(f"{e:.2f}°" + ("  keyhole" if d.get("kh") else ""),
                              T.GOOD if e < 0.5 else (T.WARNING if e < 2 else T.CRITICAL))
        else:
            self.chip_err.set("—")
        if d.get("tle_fb"):
            self.chip_tle.set(f"vechi · {d['tle_age']:.0f} zile", T.WARNING, "alert")
        else:
            self.chip_tle.set(f"actual · {d['tle_age']:.1f} zile", T.GOOD)
        for m, b in self.mode_buttons.items():
            b.setChecked((m == "DEMO" and d.get("warp", 1) > 1) or
                         (m == "AUTO" and st in ("WAIT_AOS", "ACQUIRE", "TRACK") and d.get("warp", 1) == 1) or
                         (m == "MANUAL" and st == "MANUAL") or (m == "IDLE" and st == "IDLE"))
        idx = self.sat_combo.findData(d["sat"])
        if idx >= 0 and idx != self.sat_combo.currentIndex():
            self.sat_combo.setCurrentIndex(idx)

        t = d["t_utc_unix"]
        sat = self._sat(d["sat"])
        now = time.monotonic()
        if now - self.last_orbit_update > 10.0:
            self.globe.update_orbit(sat, t)
            self.last_orbit_update = now
        self.globe.update_satellite(sat, t, d["sat_el"])
        # true antenna direction on the local sky (attitude applied)
        from ..core import geometry as G
        b = G.boresight_enu(d["ant_az"], d["ant_el"], d["roll"], d["pitch"], d["yaw"])
        a_az, a_el = G.enu_to_azel(b)
        self.sky.set_positions(d["sat_az"], d["sat_el"], a_az, a_el)
        self.veh3d.set_state(d["roll"], d["pitch"], d["yaw"], d["ant_az"], d["ant_el"], d["sat_az"], d["sat_el"])
        self.charts.update(self.store)
        if now - self.last_pass_update > 30.0:
            self._update_passes(sat, d)
            self.last_pass_update = now
        if int(now * 10) % 5 == 0:
            self.xcheck_diff = self.xcheck.difference(d)
            if self.xcheck_diff is not None:
                ok = self.xcheck_diff < 0.1
                self.chip_x.set(f"Δ {self.xcheck_diff:.3f}°", T.GOOD if ok else T.CRITICAL,
                                "check-decagram" if ok else "alert")

    def _update_passes(self, sat, d):
        t = d["t_utc_unix"]
        ps = sat.passes(t - 600, count=6, horizon_h=36)
        # sky track of the first pass that has not ended
        cur = next((p for p in ps if p.los is None or p.los > t), None)
        if cur and cur.los:
            n = 90
            az, el = [], []
            for i in range(n + 1):
                lk = sat.look(cur.aos + (cur.los - cur.aos) * i / n)
                az.append(lk.az)
                el.append(lk.el)
            self.sky.set_track(az, el)
        else:
            self.sky.set_track([], [])
        # skyfield cross-check of the rise times
        sky_rises = self._skyfield_rises(d["sat"], t - 600, (ps[-1].los or t) + 600 if ps else t)
        self.passes.setRowCount(len(ps))
        for i, p in enumerate(ps):
            fmt = lambda x: time.strftime("%d.%m %H:%M:%S", time.gmtime(x)) if x else "—"  # noqa: E731
            dur = f"{(p.los - p.aos) / 60:.1f}′" if p.los else "fix"
            diff = min((abs(r - p.aos) for r in sky_rises), default=None) if p.los else None
            vals = [fmt(p.aos)[6:] if p.los else fmt(p.aos), fmt(p.los)[6:] if p.los else "—", f"{p.max_el:.1f}°", dur,
                    f"{p.aos_az:.0f}°", f"{diff:.1f} s" if diff is not None else "—"]
            for j, v in enumerate(vals):
                it = QtWidgets.QTableWidgetItem(v)
                if cur is p:
                    it.setForeground(QtGui.QColor(T.ACCENT))
                self.passes.setItem(i, j, it)

    def _skyfield_rises(self, catnr, t0, t1):
        try:
            from skyfield.api import EarthSatellite
            name, l1, l2 = self.xcheck.tles[catnr]
            es = EarthSatellite(l1, l2, name, self.xcheck.ts)
            a = self.xcheck.ts.from_datetime(dt.datetime.fromtimestamp(t0, dt.timezone.utc))
            b = self.xcheck.ts.from_datetime(dt.datetime.fromtimestamp(t1, dt.timezone.utc))
            times, events = es.find_events(self.xcheck.site, a, b, altitude_degrees=C.MASK_EL_DEG)
            return [tt.utc_datetime().timestamp() for tt, e in zip(times, events) if e == 0]
        except Exception:  # noqa: BLE001
            return []

    def closeEvent(self, e):  # noqa: N802
        if self.link:
            self.link.stop()
        super().closeEvent(e)


_ = math
