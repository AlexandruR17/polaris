"""Screenshots of the dashboard running on the internal simulation.

The 3D panels need OpenGL: run under a virtual X server, e.g.
    xvfb-run -a -s "-screen 0 1920x1080x24" python tools/screenshots.py docs/img
(QT_QPA_PLATFORM=offscreen has no OpenGL context, the 3D panels stay black.)

Scenario: boot and homing, DEMO x30 on the next ISS pass, bumpy road.
"""
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from polaris_gs.ui import theme  # noqa: E402
from polaris_gs.ui.main_window import MainWindow  # noqa: E402


def main():
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs" / "img")
    out.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication([])
    app.setStyleSheet(theme.QSS)
    app.setFont(QtGui.QFont(theme.FONT, 10))
    w = MainWindow("sim", db_path=str(out / "_screens.sqlite"))
    w.resize(1920, 1080)
    w.move(0, 0)
    w.show()
    state = {"t0": time.monotonic(), "phase": 0, "track_t": None, "shots": []}

    def grab(name):
        app.processEvents()
        img = w.screen().grabWindow(w.winId())
        path = out / name
        img.save(str(path))
        state["shots"].append(str(path))
        print("saved", path, img.width(), "x", img.height(), "mode", w.store.last and w.store.last["mode"])

    def step():
        t = time.monotonic() - state["t0"]
        d = w.store.last
        mode = d["mode"] if d else None
        if state["phase"] == 0 and mode == "WAIT_AOS" and t > 6:
            grab("dashboard_wait.png")
            w.veh_combo.setCurrentIndex(1)  # bumpy road
            w._set_warp(30)
            w.cmd("MODE:DEMO")
            state["phase"] = 1
        elif state["phase"] == 1 and mode == "TRACK":
            state["track_t"] = state["track_t"] or t
            if t - state["track_t"] > 7:
                grab("dashboard_track.png")
                state["phase"] = 2
        elif state["phase"] == 2 and mode == "WAIT_AOS" and d.get("warp", 1) == 1:
            grab("dashboard_after_pass.png")
            app.quit()
        if t > 240:
            grab("dashboard_timeout.png")
            app.quit()

    timer = QtCore.QTimer()
    timer.timeout.connect(step)
    timer.start(200)
    app.exec()
    return 0 if state["phase"] == 2 or len(state["shots"]) >= 3 else 1


if __name__ == "__main__":
    sys.exit(main())
