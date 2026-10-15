"""Telemetry history, events and the SQLite results database."""
import collections
import json
import math
import pathlib
import sqlite3
import threading
import time

from .core import geometry as G
from .core import protocol as P

HISTORY_S = 180.0


class TelemetryStore:
    def __init__(self, maxlen=4000):
        self.last = None
        self.t0 = time.monotonic()
        self.hist = collections.deque(maxlen=maxlen)
        self.events = collections.deque(maxlen=500)
        self._prev = None

    def add_telemetry(self, d):
        now = time.monotonic() - self.t0
        az_rate = el_rate = 0.0
        if self._prev is not None:
            dt = now - self._prev[0]
            # telemetry is sent at 10 Hz; arrival jitter would distort the rate
            dt = max(dt, 0.08)
            az_rate = (d["ant_az"] - self._prev[1]) / dt
            el_rate = (d["ant_el"] - self._prev[2]) / dt
            if abs(az_rate) > 100 or abs(el_rate) > 100:  # position re-set by homing
                az_rate = el_rate = math.nan
        self._prev = (now, d["ant_az"], d["ant_el"])
        d["_t"] = now
        d["_az_rate"] = az_rate
        d["_el_rate"] = el_rate
        self.last = d
        self.hist.append(d)

    def add_event(self, d):
        d["_wall"] = time.time()
        self.events.append(d)

    def series(self, key, window=HISTORY_S):
        if not self.hist:
            return [], []
        tmax = self.hist[-1]["_t"]
        xs, ys = [], []
        for d in self.hist:
            if d["_t"] >= tmax - window:
                xs.append(d["_t"] - tmax)
                v = d.get(key)
                ys.append(float(v) if v is not None else math.nan)
        return xs, ys


SCHEMA = """
CREATE TABLE IF NOT EXISTS passes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    saved_utc TEXT NOT NULL,
    link TEXT, sat INTEGER, los_utc TEXT,
    comp INTEGER, warp INTEGER, vehicle TEXT,
    max_err REAL, rms_err REAL, n INTEGER
);
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    saved_utc TEXT NOT NULL,
    name TEXT, sat INTEGER, aos_utc TEXT, max_el REAL,
    vehicle TEXT, comp INTEGER, warp INTEGER, planner INTEGER,
    max_err REAL, rms_err REAL, p95_err REAL, n INTEGER, extra TEXT
);
"""


class ResultsDB:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # the web server saves from the link thread and reads from the page thread
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript(SCHEMA)

    def save_pass(self, ev, link, vehicle):
        with self.lock:
            self._save_pass(ev, link, vehicle)

    def _save_pass(self, ev, link, vehicle):
        self.db.execute(
            "INSERT INTO passes (saved_utc, link, sat, los_utc, comp, warp, vehicle, max_err, rms_err, n)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (P.iso_utc(time.time()), link, ev.get("sat"), ev.get("t_utc"), ev.get("comp"),
             ev.get("warp"), vehicle, ev.get("max_err"), ev.get("rms_err"), ev.get("n")))
        self.db.commit()

    def save_experiment(self, **kw):
        extra = kw.pop("extra", None)
        cols = ["saved_utc"] + list(kw) + ["extra"]
        vals = [P.iso_utc(time.time())] + list(kw.values()) + [json.dumps(extra) if extra else None]
        with self.lock:
            self._insert(cols, vals)

    def _insert(self, cols, vals):
        self.db.execute(f"INSERT INTO experiments ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        vals)
        self.db.commit()

    def passes(self, limit=50):
        with self.lock:
            cur = self.db.execute("SELECT saved_utc, link, sat, los_utc, comp, warp, vehicle, max_err, rms_err, n"
                                  " FROM passes ORDER BY id DESC LIMIT ?", (limit,))
            return cur.fetchall()
