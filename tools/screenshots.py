"""Screenshots of the web dashboard running on the internal simulation.

Starts `python -m polaris_gs` on a free port, drives the page in headless
Chromium (Playwright) like a user would, and saves PNGs. Fails if the page
logs a JavaScript error.

usage: python tools/screenshots.py [out_dir]   (default docs/img)
       CHROMIUM=/path/to/chrome to choose the browser binary
Scenario: boot and homing, bumpy road, DEMO x30 on the next ISS pass.
"""
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs" / "img")
    out.mkdir(parents=True, exist_ok=True)
    port = free_port()
    db = pathlib.Path(tempfile.mkdtemp()) / "shots.sqlite"
    srv = subprocess.Popen([sys.executable, "-m", "polaris_gs", "--no-browser", "--port", str(port), "--db", str(db)],
                           cwd=ROOT / "ground_station")
    errors = []
    try:
        time.sleep(2.0)
        with sync_playwright() as p:
            exe = os.environ.get("CHROMIUM")
            b = p.chromium.launch(executable_path=exe or None, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            pg = b.new_page(viewport={"width": 1920, "height": 1080})
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{port}/")
            pg.wait_for_function("document.querySelector('#state-text').textContent.includes('Așteptare')",
                                 timeout=30000)
            time.sleep(4.0)                     # orbit and passes arrive at 2 Hz
            pg.screenshot(path=str(out / "dashboard_wait.png"))
            pg.select_option("#veh-select", "bumpy")
            pg.click("#mode-btns button[data-mode=DEMO]")
            pg.wait_for_function("document.querySelector('#state-text').textContent.includes('Urmărire')",
                                 timeout=60000)
            time.sleep(8.0)
            pg.screenshot(path=str(out / "dashboard_track.png"))
            pg.wait_for_function("document.querySelector('#log').textContent.includes('LOS')", timeout=120000)
            time.sleep(3.0)
            pg.click(".tab[data-tab=results]")
            pg.click(".tab[data-chart=att]")
            time.sleep(0.5)
            pg.screenshot(path=str(out / "dashboard_after_pass.png"))
            pg.set_viewport_size({"width": 390, "height": 844})
            time.sleep(1.5)
            pg.screenshot(path=str(out / "dashboard_phone.png"), full_page=True)
            b.close()
    finally:
        srv.terminate()
        srv.wait(5)
    if errors:
        print("JavaScript errors:\n  " + "\n  ".join(errors))
        sys.exit(1)
    print("written", out)


if __name__ == "__main__":
    main()
