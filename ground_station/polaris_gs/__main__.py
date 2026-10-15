"""POLARIS Ground Station.

python -m polaris_gs                       internal simulation (no Wokwi needed)
python -m polaris_gs --link rfc2217://localhost:4000   Wokwi for VS Code
python -m polaris_gs --link COM3           real ESP32 on a serial port
"""
import argparse
import pathlib
import sys

from PySide6 import QtGui, QtWidgets


def main(argv=None):
    ap = argparse.ArgumentParser(prog="polaris_gs")
    ap.add_argument("--link", default="sim", help="sim, rfc2217://host:port or a serial port")
    ap.add_argument("--db", default=str(pathlib.Path.home() / ".polaris" / "polaris.sqlite"),
                    help="SQLite file for pass results")
    ap.add_argument("--online-tle", action="store_true",
                    help="simulation downloads TLEs from CelesTrak instead of the stored ones")
    ap.add_argument("--size", default="1920x1080")
    args = ap.parse_args(argv)

    app = QtWidgets.QApplication(sys.argv[:1])
    from .ui import theme
    from .ui.main_window import MainWindow
    app.setStyleSheet(theme.QSS)
    app.setFont(QtGui.QFont(theme.FONT, 10))
    w = MainWindow(args.link, args.db, args.online_tle)
    wd, ht = (int(x) for x in args.size.split("x"))
    w.resize(wd, ht)
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
