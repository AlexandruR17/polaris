"""Serial protocol: JSON lines from the ESP32, text commands to it.

Mirrored in firmware/lib/polaris_core/protocol.cpp (command parsing).
"""
import json
import math
import time
from dataclasses import dataclass

TELEMETRY_KEYS = ("t_utc", "sat", "sat_az", "sat_el", "range_km", "cmd_az", "cmd_el",
                  "ant_az", "ant_el", "roll", "pitch", "yaw", "err_deg", "mode",
                  "next_aos", "next_los", "max_el")

EVENTS = ("BOOT", "AOS", "LOS", "HOME_OK", "ESTOP", "FAULT", "MODE", "TLE_OK",
          "TLE_FALLBACK", "KEYHOLE", "RATE_LIMIT", "WRAP", "PASS", "ACK", "CMD", "ERR", "INFO")

STATES = ("BOOT", "HOMING", "IDLE", "WAIT_AOS", "ACQUIRE", "TRACK", "STOW", "MANUAL",
          "DEMO", "ESTOP", "FAULT")

MODES = ("AUTO", "MANUAL", "DEMO", "IDLE", "STOW")

MAX_JOG_DEG = 90.0
MAX_TILT_DEG = 45.0


@dataclass
class Command:
    name: str
    args: tuple = ()


def parse_command(line):
    """Parse one command line. Raises ValueError with a short reason."""
    s = line.strip()
    if not s:
        raise ValueError("empty")
    name, _, rest = s.partition(":")
    name = name.strip().upper()
    rest = rest.strip()
    if name in ("HOME", "STOW", "ACK"):
        if rest:
            raise ValueError("no args")
        return Command(name)
    if name == "SAT":
        if not rest.isdigit() or len(rest) > 9 or not rest.isascii():
            raise ValueError("bad id")
        return Command(name, (int(rest),))
    if name == "MODE":
        m = rest.upper()
        if m not in MODES:
            raise ValueError("bad mode")
        return Command(name, (m,))
    if name == "WARP":
        try:
            w = int(rest)
        except ValueError:
            raise ValueError("bad warp") from None
        if w not in (1, 10, 30, 60):
            raise ValueError("bad warp")
        return Command(name, (w,))
    if name == "COMP":
        if rest not in ("0", "1"):
            raise ValueError("bad comp")
        return Command(name, (rest == "1",))
    if name == "VEH":
        if rest.upper() == "OFF":
            return Command(name, ())
        parts = rest.split(",")
        if len(parts) != 3:
            raise ValueError("bad veh")
        try:
            r, p, y = (float(x) for x in parts)
        except ValueError:
            raise ValueError("bad veh") from None
        if not all(math.isfinite(v) for v in (r, p, y)):
            raise ValueError("bad veh")
        if abs(r) > MAX_TILT_DEG or abs(p) > MAX_TILT_DEG:
            raise ValueError("tilt range")
        return Command(name, (r, p, y))
    if name == "JOG":
        parts = rest.split(",")
        if len(parts) != 2 or parts[0].strip().upper() not in ("AZ", "EL"):
            raise ValueError("bad jog")
        try:
            d = float(parts[1])
        except ValueError:
            raise ValueError("bad jog") from None
        if not math.isfinite(d) or abs(d) > MAX_JOG_DEG:
            raise ValueError("jog range")
        return Command(name, (parts[0].strip().upper(), d))
    raise ValueError("unknown")


def sanitize(s, n=64):
    """Keep printable ASCII without quotes or backslashes (same as C++)."""
    out = [c for c in s if 32 <= ord(c) < 127 and c not in '"\\']
    return "".join(out)[: n - 1]


def format_command(name, *args):
    if not args:
        return f"{name}\n"
    def fmt(a):
        if isinstance(a, bool):
            return "1" if a else "0"
        if isinstance(a, float):
            return f"{a:.2f}"
        return str(a)
    return f"{name}:{','.join(fmt(a) for a in args)}\n"


def iso_utc(t):
    if t is None:
        return None
    tt = time.gmtime(int(math.floor(t)))
    tenth = int((t - math.floor(t)) * 10.0)
    return time.strftime("%Y-%m-%dT%H:%M:%S", tt) + f".{tenth}Z"


def parse_iso_utc(s):
    """'2026-10-14T22:05:03.1Z' -> unix seconds. Works on Python 3.10."""
    if s is None:
        return None
    import calendar
    s = s.rstrip("Z")
    base, _, frac = s.partition(".")
    tt = time.strptime(base, "%Y-%m-%dT%H:%M:%S")
    return calendar.timegm(tt) + (float("0." + frac) if frac else 0.0)


def parse_line(line):
    """Return ('telemetry'|'event', dict) or None for non JSON lines."""
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict):
        return None
    if "ev" in d:
        return "event", d
    if all(k in d for k in TELEMETRY_KEYS):
        for k in ("t_utc", "next_aos", "next_los"):
            if isinstance(d.get(k), str):
                d[k + "_unix"] = parse_iso_utc(d[k])
        return "telemetry", d
    return None


def telemetry_line(d):
    return json.dumps(d, separators=(",", ":"))


def event_line(ev, **kw):
    d = {"ev": ev}
    d.update(kw)
    return json.dumps(d, separators=(",", ":"))
