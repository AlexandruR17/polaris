"""Smoke test of the real firmware binary in Espressif QEMU.

Builds nothing: run `pio run -e esp32dev_qemu` first. QEMU has no WiFi radio,
ADC or I2C devices, so the firmware runs on its fallback TLE and build time.
The script talks to the firmware over the emulated UART (TCP) like the
dashboard does, and checks the event sequence.

usage: python tools/qemu_smoke.py <qemu-system-xtensa> [--log out.txt]
"""
import argparse
import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMAGE = ROOT / "firmware/.pio/build/esp32dev_qemu/firmware.factory.bin"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("qemu")
    ap.add_argument("--log", default=None)
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--timeout", type=float, default=240.0)
    args = ap.parse_args()

    flash = pathlib.Path(tempfile.mkdtemp()) / "flash.bin"
    data = IMAGE.read_bytes()
    img = bytearray(b"\xff" * (4 * 1024 * 1024))
    img[: len(data)] = data
    flash.write_bytes(img)
    proc = subprocess.Popen(
        [args.qemu, "-nographic", "-machine", "esp32", "-drive", f"file={flash},if=mtd,format=raw",
         "-global", "driver=timer.esp32.timg,property=wdt_disable,value=true",
         "-serial", f"tcp::{args.port},server", "-monitor", "none"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sock = None
    for _ in range(50):
        try:
            sock = socket.create_connection(("127.0.0.1", args.port), timeout=1)
            break
        except OSError:
            time.sleep(0.2)
    if sock is None:
        print("cannot connect to QEMU serial")
        return 2
    sock.settimeout(0.5)
    log = open(args.log, "w") if args.log else None
    events, telem = [], 0
    buf = b""
    sent = set()
    t0 = time.time()
    steps = [  # (event that triggers it, command)
        ("HOME_OK", "MODE:MANUAL"),
        ("MANUAL", "JOG:AZ,30"),
        ("JOG", "SAT:43700"),
        ("SAT", "MODE:AUTO"),
        ("TRACK", "VEH:5,-3,120"),
        ("VEH", "MODE:STOW"),
        ("STOW", "HOME"),
    ]
    ok = False
    while time.time() - t0 < args.timeout:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            chunk = b""
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            text = line.decode(errors="replace").strip()
            if log:
                log.write(text + "\n")
            if not text.startswith("{"):
                continue
            try:
                d = json.loads(text)
            except json.JSONDecodeError:
                continue
            if "ev" in d:
                tag = d["ev"] if d["ev"] != "MODE" else d["to"]
                if d["ev"] == "CMD":
                    tag = d["cmd"].split(":")[0]
                events.append(tag)
                print(f"{time.time() - t0:6.1f}s  {text[:150]}")
                for trig, cmd in steps:
                    if trig == tag and cmd not in sent:
                        sent.add(cmd)
                        sock.sendall((cmd + "\n").encode())
                if tag == "HOME_OK" and "HOME" in sent:
                    ok = True
            else:
                telem += 1
        if ok:
            break
    proc.terminate()
    print(f"telemetry lines: {telem}, events: {len(events)}")
    need = ["BOOT", "TLE_FALLBACK", "TLE", "HOMING", "HOME_OK", "MANUAL", "STOW", "ACQUIRE", "TRACK"]
    missing = [e for e in need if e not in events]
    print("RESULT:", "PASS" if ok and not missing and telem > 50 else f"FAIL missing={missing}")
    return 0 if ok and not missing else 1


if __name__ == "__main__":
    sys.exit(main())
