"""Ground station logic shared by every front end: owns the link, the
telemetry history, the results database, the skyfield cross-check and the
vehicle motion stream. It talks to the page through JSON messages.

Messages to the page (field "t"):
  hello    link, satellites, warps, vehicle modes, current settings
  status   link status text
  tm       one telemetry frame plus derived values (antenna sky direction,
           axis rates, satellite sub-point and altitude)
  ev       one controller event
  history  last two minutes of chart data (sent to a new page)
  orbit    orbit and ground track, Earth-fixed, in Earth radii
  passes   next passes with the skyfield rise check and the sky track
  xcheck   skyfield difference
  results  passes saved in SQLite
Messages from the page (field "op"):
  cmd {text}, link {spec}, vehicle {mode}, veh_send {on}, estop {on},
  limit {axis, on}
"""
import collections
import datetime as dt
import math
import threading
import time

from .core import config as C
from .core import geometry as G
from .core import protocol as P
from .core.orbit import WGS84_A, Satellite, ecef_to_geodetic, site_ecef
from .crosscheck import CrossCheck
from .link import SerialLink, SimLink
from .store import ResultsDB, TelemetryStore
from .vehicle import MODES as VEH_MODES
from .vehicle import VehicleMotion

SAT_NAMES = {25544: "ISS", 33591: "NOAA 19", 28654: "NOAA 18", 43700: "QO-100 (geostaționar)"}
LINKS = [("sim", "Simulare internă"), ("rfc2217://localhost:4000", "Wokwi (rfc2217://localhost:4000)"),
         ("port", "Port serial…")]
CHART_WINDOW_S = 120.0


def r3(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 3)


class GroundStation:
    def __init__(self, emit, db_path=None, online_tle=False):
        self.emit = emit                 # thread-safe: emit(dict)
        self.online_tle = online_tle
        self.db = ResultsDB(db_path) if db_path else None
        self.xcheck = CrossCheck()
        self.store = TelemetryStore()
        self.events = collections.deque(maxlen=200)
        self.vehicle = VehicleMotion("stationary")
        self.veh_mode = "stationary"
        self.veh_send = True
        self.veh_t0 = time.monotonic()
        self.estop = False
        self.limit_az = False
        self.link = None
        self.spec = None
        self.sats = {}
        self.sat_id = C.DEFAULT_SAT
        self.orbit_due = self.passes_due = 0.0
        self.tle_query_at = 0.0
        self.last_orbit = self.last_passes = self.last_xcheck = None
        self._lock = threading.RLock()
        self.station = [c / WGS84_A for c in site_ecef(C.STATION_LAT_DEG, C.STATION_LON_DEG, C.STATION_ALT_M)]

    # ------------------------------------------------------------ link
    def connect(self, spec):
        old = self.link
        if old:
            old.on_line = lambda text: None
            old.on_status = lambda text, ok: None
            old.stop()
        with self._lock:
            self.spec = spec
            self.store = TelemetryStore()
            self.estop = self.limit_az = False
            self.orbit_due = self.passes_due = 0.0
        if spec == "sim":
            self.link = SimLink(self.online_tle, self.on_line, self.on_status)
        else:
            self.link = SerialLink(spec, self.on_line, self.on_status)
        self.emit(self.hello())
        self.link.start()

    def stop(self):
        if self.link:
            self.link.stop()

    def on_status(self, text, ok):
        self.emit({"t": "status", "text": text, "ok": ok, "sim": self.link.is_sim if self.link else False})

    def send(self, text):
        if self.link:
            self.link.send(text)

    # ------------------------------------------------------------ messages from the page
    def handle(self, msg):
        op = msg.get("op")
        if op == "cmd":
            text = str(msg.get("text", "")).strip()
            if text:
                self.send(text)
            return
        elif op == "link":
            spec = str(msg.get("spec", "")).strip()
            if spec:
                self.connect(spec)
        elif op == "vehicle":
            mode = msg.get("mode")
            if mode in VEH_MODES:
                self.veh_mode = mode
                self.vehicle.set_mode(mode)
                self.veh_t0 = time.monotonic()
        elif op == "veh_send":
            self.veh_send = bool(msg.get("on"))
            if not self.veh_send:
                self.send("VEH:OFF")
        elif op == "estop" and isinstance(self.link, SimLink):
            self.estop = bool(msg.get("on"))
            self.link.set_estop(self.estop)
        elif op == "limit" and isinstance(self.link, SimLink):
            self.limit_az = bool(msg.get("on"))
            self.link.set_limit("AZ", self.limit_az)
        else:
            return
        self.emit(self.settings())

    def settings(self):
        return {"t": "settings", "vehicle": self.veh_mode, "veh_send": self.veh_send,
                "estop": self.estop, "limit": self.limit_az}

    def hello(self):
        return {
            "t": "hello",
            "link": {"spec": self.spec, "name": self.link.name if self.link else "",
                     "sim": bool(self.link and self.link.is_sim),
                     "text": self.link.status_text if self.link else "", "ok": bool(self.link and self.link.connected)},
            "links": LINKS,
            "sats": [[k, v] for k, v in SAT_NAMES.items()],
            "warps": list(C.DEMO_WARPS),
            "default_warp": C.DEFAULT_DEMO_WARP,
            "vehicle_modes": [[k, v] for k, v in VEH_MODES.items()],
            "station": {"lat": C.STATION_LAT_DEG, "lon": C.STATION_LON_DEG, "alt_m": C.STATION_ALT_M,
                        "ecef": self.station},
            "mask_el": C.MASK_EL_DEG,
            **{k: v for k, v in self.settings().items() if k != "t"},
        }

    def snapshot(self):
        """Everything a newly opened page needs, in order."""
        out = [self.hello(), self.history()]
        out += [{"t": "ev", "d": d} for d in list(self.events)[-60:]]
        if self.last_orbit:
            out.append(self.last_orbit)
        if self.last_passes:
            out.append(self.last_passes)
        if self.last_xcheck:
            out.append(self.last_xcheck)
        out.append(self.results())
        return out

    # ------------------------------------------------------------ incoming protocol lines
    def on_line(self, text):
        # called inside the controller loop: never let an error travel back into it
        try:
            self._on_line(text)
        except Exception as e:  # noqa: BLE001
            print(f"[polaris] line not processed ({e!r}): {text[:120]}")

    def _on_line(self, text):
        parsed = P.parse_line(text)
        if not parsed:
            return
        kind, d = parsed
        if kind == "telemetry":
            with self._lock:
                self.store.add_telemetry(d)
                if d["sat"] != self.sat_id:
                    self.sat_id = d["sat"]
                    self.orbit_due = self.passes_due = 0.0
            self.emit({"t": "tm", "d": self._frame(d)})
            return
        d["_wall"] = time.time()
        ev = d["ev"]
        if ev == "CMD" and str(d.get("cmd", "")).upper().startswith(("VEH", "TLE")):
            return  # 10 Hz vehicle stream and our own TLE queries: keep the log readable
        if ev == "TLE" and d.get("l1") and d.get("l2"):
            # check skyfield against the elements the controller really uses
            self.xcheck.set_tle(int(d["sat"]), str(d.get("name", "")).strip(), d["l1"], d["l2"])
            self.orbit_due = self.passes_due = 0.0
        self.events.append(d)
        if ev == "LOS" and self.db:
            self.db.save_pass(d, self.link.name if self.link else "", self.veh_mode)
            self.emit(self.results())
        if ev in ("PASS", "TLE_OK", "TLE_FALLBACK"):
            self.orbit_due = self.passes_due = 0.0
        self.emit({"t": "ev", "d": d})

    def _sat(self, catnr):
        if catnr not in self.xcheck.tles:
            return None
        name, l1, l2 = self.xcheck.tles[catnr]
        key = (catnr, l1)
        if key not in self.sats:
            self.sats[key] = Satellite(name, l1, l2)
        return self.sats[key]

    def _frame(self, d):
        """Telemetry plus what the page should not have to compute."""
        out = {k: v for k, v in d.items() if not k.startswith("_")}
        b = G.boresight_enu(d["ant_az"], d["ant_el"], d["roll"], d["pitch"], d["yaw"])
        a_az, a_el = G.enu_to_azel(b)
        out.update(ant_sky_az=r3(a_az), ant_sky_el=r3(a_el), az_rate=r3(d["_az_rate"]),
                   el_rate=r3(d["_el_rate"]), _t=round(d["_t"], 2))
        sat = self._sat(d["sat"])
        if sat is not None:
            r = sat.look(d["t_utc_unix"]).r_ecef
            lat, lon, h = ecef_to_geodetic(r)
            out.update(sat_ecef=[round(c / WGS84_A, 5) for c in r], sat_lat=r3(lat), sat_lon=r3(lon),
                       sat_alt_km=round(h, 1))
        return out

    def history(self):
        with self._lock:
            hist = list(self.store.hist)
        if not hist:
            return {"t": "history", "rows": []}
        tmax = hist[-1]["_t"]
        rows = [[round(d["_t"], 2), r3(d["err_deg"]), d["mode"], r3(d["_az_rate"]), r3(d["_el_rate"]),
                 r3(d["roll"]), r3(d["pitch"])] for d in hist if d["_t"] >= tmax - CHART_WINDOW_S]
        return {"t": "history", "rows": rows}

    def results(self):
        rows = []
        if self.db:
            for saved, link, sat, los, comp, warp, veh, mx, rms, n in self.db.passes(12):
                rows.append({"saved": saved, "link": link, "sat": sat, "los": los, "comp": comp, "warp": warp,
                             "vehicle": VEH_MODES.get(veh, veh), "max_err": mx, "rms_err": rms, "n": n})
        return {"t": "results", "rows": rows, "db": str(self.db.path) if self.db else None}

    # ------------------------------------------------------------ periodic work
    def tick_vehicle(self):
        """10 Hz: the laptop plays the vehicle IMU (VEH command). Only while the
        controller is alive and past BOOT: during setup() it does not read the
        serial port and the commands would overflow its buffer."""
        if not self.veh_send or not self.link or not self.link.connected:
            return
        last = self.store.last
        if last is None or last["mode"] == "BOOT" or time.monotonic() - self.store.t0 - last["_t"] > 1.0:
            return
        r, p, y = self.vehicle.attitude(time.monotonic() - self.veh_t0)
        self.send(P.format_command("VEH", r, p, y).strip())

    def tick_slow(self):
        """2 Hz: skyfield check, orbit every 10 s, passes every 30 s. Runs off the event loop."""
        d = self.store.last
        if d is None:
            return
        sat = self._sat(d["sat"])
        if sat is not None and abs(sat.age_days(d["t_utc_unix"]) - d["tle_age"]) > 0.15:
            # not the controller's TLE (e.g. it downloaded a fresh one): ask for it
            now = time.monotonic()
            if now - self.tle_query_at > 10.0:
                self.tle_query_at = now
                self.send("TLE")
            self.last_xcheck = {"t": "xcheck", "diff": None, "note": "aștept TLE"}
            self.emit(self.last_xcheck)
            return
        diff = self.xcheck.difference(d)
        if diff is not None:
            self.last_xcheck = {"t": "xcheck", "diff": round(diff, 4)}
            self.emit(self.last_xcheck)
        if sat is None:
            return
        now = time.monotonic()
        if now >= self.orbit_due:
            self.orbit_due = now + 10.0
            self.last_orbit = self._orbit(sat, d["t_utc_unix"])
            self.emit(self.last_orbit)
        if now >= self.passes_due:
            self.passes_due = now + 30.0
            self.last_passes = self._passes(sat, d)
            self.emit(self.last_passes)

    def _orbit(self, sat, t):
        period = 86164.0 if sat.is_geo else 86400.0 / sat.mean_motion_rev_day
        pos, track = [], []
        for i in range(241):
            r = sat.look(t + period * (i / 240.0 - 0.5)).r_ecef
            p = [c / WGS84_A for c in r]
            n = math.sqrt(sum(c * c for c in p))
            pos.append([round(c, 4) for c in p])
            track.append([round(c / n, 4) for c in p])
        return {"t": "orbit", "sat": sat.catnr, "pos": pos, "track": track}

    def _passes(self, sat, d):
        t = d["t_utc_unix"]
        ps = sat.passes(t - 600, count=6, horizon_h=36)
        cur = next((p for p in ps if p.los is None or p.los > t), None)
        sky = {"az": [], "el": []}
        if cur and cur.los:
            for i in range(91):
                lk = sat.look(cur.aos + (cur.los - cur.aos) * i / 90)
                sky["az"].append(round(lk.az, 2))
                sky["el"].append(round(lk.el, 2))
        end = (ps[-1].los or t) + 600 if ps else t
        rises = self._skyfield_rises(d["sat"], t - 600, end)
        rows = []
        for p in ps:
            diff = min((abs(r - p.aos) for r in rises), default=None) if p.los else None
            rows.append({"aos": p.aos, "los": p.los, "tmax": p.tmax, "max_el": round(p.max_el, 1), "aos_az": round(p.aos_az),
                         "dur_min": round((p.los - p.aos) / 60, 1) if p.los else None,
                         "sky_diff_s": round(diff, 1) if diff is not None else None, "current": p is cur})
        return {"t": "passes", "sat": sat.catnr, "rows": rows, "sky": sky}

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
