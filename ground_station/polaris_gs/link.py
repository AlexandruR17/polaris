"""Links to the antenna controller: real serial port, Wokwi RFC2217, or the
internal Python copy of the firmware. All of them speak the same protocol."""
import threading
import time
import urllib.request

from PySide6 import QtCore

from .core import config as C
from .core.tle_data import CELESTRAK_URL
from .sim.runner import DT_MS, SimRig


class Link(QtCore.QObject):
    line = QtCore.Signal(str)
    status = QtCore.Signal(str, bool)   # text, connected

    name = "link"

    def start(self):
        raise NotImplementedError

    def stop(self):
        pass

    def send(self, cmd):
        raise NotImplementedError


class SerialLink(Link):
    """pyserial URL: 'rfc2217://localhost:4000' (Wokwi VS Code) or 'COM3', '/dev/ttyUSB0'."""

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.name = url
        self._ser = None
        self._run = False
        self._thread = None
        self._lock = threading.Lock()

    def start(self):
        self._run = True
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        import serial
        while self._run:
            try:
                self.status.emit(f"Conectare la {self.url}...", False)
                ser = serial.serial_for_url(self.url, baudrate=115200, timeout=0.2)
                with self._lock:
                    self._ser = ser
                self.status.emit(f"Conectat: {self.url}", True)
                buf = b""
                while self._run:
                    chunk = ser.read(512)
                    if not chunk:
                        continue
                    buf += chunk
                    while b"\n" in buf:
                        raw, buf = buf.split(b"\n", 1)
                        self.line.emit(raw.decode(errors="replace").rstrip("\r"))
            except Exception as e:  # noqa: BLE001 - any port error: retry
                self.status.emit(f"Fără legătură ({e.__class__.__name__}), reîncerc...", False)
                with self._lock:
                    self._ser = None
                time.sleep(2.0)

    def stop(self):
        self._run = False
        with self._lock:
            if self._ser:
                self._ser.close()

    def send(self, cmd):
        with self._lock:
            if self._ser:
                self._ser.write((cmd.strip() + "\n").encode())


class SimLink(Link):
    """Runs the Python copy of the firmware in real time (50 Hz control loop)."""

    tle_ready = QtCore.Signal(int, str, str, str, bool)

    def __init__(self, online_tle=False):
        super().__init__()
        self.name = "simulare internă"
        self.online = online_tle
        self.rig = None
        self.timer = QtCore.QTimer(self)
        self.timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.tle_ready.connect(self._on_tle)
        self.ms = 0
        self._t_start = 0.0
        self._booted = False

    def _emit(self, text):
        self.line.emit(text)

    def start(self):
        now = time.time()
        self.rig = SimRig(self._emit, now)
        self._emit('{"ev":"INFO","msg":"MPU_MISSING"}')
        self._emit('{"ev":"INFO","msg":"SIM_LINK"}')
        self._t_start = time.monotonic()
        self.ms = 0
        self._booted = False
        self.status.emit("Simulare internă (copia firmware-ului)", True)
        self.timer.start(10)

    def stop(self):
        self.timer.stop()

    def _tick(self):
        target = int((time.monotonic() - self._t_start) * 1000)
        steps = 0
        while self.ms + DT_MS <= target and steps < 25:
            self.ms += DT_MS
            t_real = time.time()
            if not self._booted and self.ms >= 300:
                self.rig.inp.ms = self.ms
                self.rig.inp.t_real = t_real
                if self.online:
                    self._fetch(C.DEFAULT_SAT)
                else:
                    self.rig.ctl.tle_download_failed(C.DEFAULT_SAT, t_real)
                self.rig.ctl.boot_done(self.rig.inp)
                self._booted = True
            o = self.rig.step(self.ms, t_real)
            if o.tle_request:
                if self.online:
                    self._fetch(o.tle_request)
                else:
                    self.rig.ctl.tle_download_failed(o.tle_request, t_real)
            steps += 1
        if steps == 25:  # fell behind (window was busy): drop the backlog
            self.ms = target

    def _fetch(self, catnr):
        def work():
            try:
                with urllib.request.urlopen(CELESTRAK_URL.format(catnr=catnr), timeout=8) as r:
                    lines = [ln.strip() for ln in r.read().decode().splitlines() if ln.strip()]
                self.tle_ready.emit(catnr, lines[0], lines[1], lines[2], True)
            except Exception:  # noqa: BLE001
                self.tle_ready.emit(catnr, "", "", "", False)
        threading.Thread(target=work, daemon=True).start()

    def _on_tle(self, catnr, name, l1, l2, ok):
        if ok and self.rig.ctl.load_tle(catnr, name, l1, l2, False, time.time(), True):
            return
        self.rig.ctl.tle_download_failed(catnr, time.time())

    def send(self, cmd):
        if self.rig:
            # the firmware echoes commands from the serial line: same here
            self.rig.ctl.command(cmd.strip())

    # operator panel shortcuts (the sim has no physical buttons)
    def press(self, button):
        if self.rig:
            setattr(self.rig.inp, button, True)

    def set_estop(self, pressed):
        if self.rig:
            self.rig.inp.estop = pressed

    def set_limit(self, axis, active):
        if self.rig:
            setattr(self.rig.inp, "lim_az" if axis == "AZ" else "lim_el", active)
