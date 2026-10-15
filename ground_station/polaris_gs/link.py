"""Links to the antenna controller: real serial port, Wokwi RFC2217, or the
internal Python copy of the firmware. All of them speak the same protocol.

A link runs in its own thread and reports through two callbacks:
on_line(text) for every protocol line and on_status(text, connected).
"""
import threading
import time
import urllib.request

from .core import config as C
from .core.tle_data import CELESTRAK_URL
from .sim.runner import DT_MS, SimRig


class Link:
    name = "link"
    is_sim = False

    def __init__(self, on_line=None, on_status=None):
        self.on_line = on_line or (lambda text: None)
        self.on_status = on_status or (lambda text, ok: None)
        self.status_text, self.connected = "", False

    def _status(self, text, ok):
        self.status_text, self.connected = text, ok
        self.on_status(text, ok)

    def start(self):
        raise NotImplementedError

    def stop(self):
        pass

    def send(self, cmd):
        raise NotImplementedError


class SerialLink(Link):
    """pyserial URL: 'rfc2217://localhost:4000' (Wokwi VS Code) or 'COM3', '/dev/ttyUSB0'."""

    def __init__(self, url, on_line=None, on_status=None):
        super().__init__(on_line, on_status)
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
                self._status(f"Conectare la {self.url}...", False)
                ser = serial.serial_for_url(self.url, baudrate=115200, timeout=0.2)
                with self._lock:
                    self._ser = ser
                self._status(f"Conectat: {self.url}", True)
                buf = b""
                while self._run:
                    chunk = ser.read(512)
                    if not chunk:
                        continue
                    buf += chunk
                    while b"\n" in buf:
                        raw, buf = buf.split(b"\n", 1)
                        self.on_line(raw.decode(errors="replace").rstrip("\r"))
            except Exception as e:  # noqa: BLE001 - any port error: retry
                if not self._run:
                    break
                self._status(f"Fără legătură ({e.__class__.__name__}), reîncerc...", False)
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

    is_sim = True

    def __init__(self, online_tle=False, on_line=None, on_status=None):
        super().__init__(on_line, on_status)
        self.name = "simulare internă"
        self.online = online_tle
        self.rig = None
        self.ms = 0
        self._booted = False
        self._run = False
        self._thread = None
        self._lock = threading.Lock()   # the rig is shared with send() and the buttons

    def start(self):
        with self._lock:
            self.rig = SimRig(self.on_line, time.time())
            self.ms = 0
            self._booted = False
        self.on_line('{"ev":"INFO","msg":"MPU_MISSING"}')
        self.on_line('{"ev":"INFO","msg":"SIM_LINK"}')
        self._status("Simulare internă (copia firmware-ului)", True)
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._run = False
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)

    def _loop(self):
        t_start = time.monotonic()
        while self._run:
            target = int((time.monotonic() - t_start) * 1000)
            steps = 0
            while self.ms + DT_MS <= target and steps < 25:
                try:
                    self._step()
                except Exception as e:  # noqa: BLE001 - report, keep the simulation alive
                    self.on_line('{"ev":"ERR","msg":"SIM_%s"}' % e.__class__.__name__)
                steps += 1
            if steps == 25:  # fell behind: drop the backlog
                self.ms = target
            time.sleep(0.005)

    def _step(self):
        with self._lock:
            self.ms += DT_MS
            t_real = time.time()
            rig = self.rig
            if not self._booted and self.ms >= 300:
                rig.inp.ms = self.ms
                rig.inp.t_real = t_real
                if self.online:
                    self._fetch(C.DEFAULT_SAT)
                else:
                    rig.ctl.tle_download_failed(C.DEFAULT_SAT, t_real)
                rig.ctl.boot_done(rig.inp)
                self._booted = True
            o = rig.step(self.ms, t_real)
            if o.tle_request:
                if self.online:
                    self._fetch(o.tle_request)
                else:
                    rig.ctl.tle_download_failed(o.tle_request, t_real)

    def _fetch(self, catnr):
        def work():
            try:
                with urllib.request.urlopen(CELESTRAK_URL.format(catnr=catnr), timeout=8) as r:
                    lines = [ln.strip() for ln in r.read().decode().splitlines() if ln.strip()]
                self._on_tle(catnr, lines[0], lines[1], lines[2], True)
            except Exception:  # noqa: BLE001
                self._on_tle(catnr, "", "", "", False)
        threading.Thread(target=work, daemon=True).start()

    def _on_tle(self, catnr, name, l1, l2, ok):
        with self._lock:
            if ok and self.rig.ctl.load_tle(catnr, name, l1, l2, False, time.time(), True):
                return
            self.rig.ctl.tle_download_failed(catnr, time.time())

    def send(self, cmd):
        with self._lock:
            if self.rig:
                self.rig.ctl.command(cmd.strip())

    # operator panel shortcuts (the sim has no physical buttons)
    def press(self, button):
        with self._lock:
            if self.rig:
                setattr(self.rig.inp, button, True)

    def set_estop(self, pressed):
        with self._lock:
            if self.rig:
                self.rig.inp.estop = pressed

    def set_limit(self, axis, active):
        with self._lock:
            if self.rig:
                setattr(self.rig.inp, "lim_az" if axis == "AZ" else "lim_el", active)
