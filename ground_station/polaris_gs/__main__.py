"""POLARIS Ground Station (web page served on http://localhost:8080).

python -m polaris_gs                                   internal simulation (no Wokwi needed)
python -m polaris_gs --link rfc2217://localhost:4000   Wokwi for VS Code
python -m polaris_gs --link COM3                       real ESP32 on a serial port
"""
import argparse
import pathlib
import threading
import webbrowser

from aiohttp import web

from .server import create_app


def main(argv=None):
    ap = argparse.ArgumentParser(prog="polaris_gs")
    ap.add_argument("--link", default="sim", help="sim, rfc2217://host:port or a serial port")
    ap.add_argument("--db", default=str(pathlib.Path.home() / ".polaris" / "polaris.sqlite"),
                    help="SQLite file for pass results")
    ap.add_argument("--online-tle", action="store_true",
                    help="simulation downloads TLEs from CelesTrak instead of the stored ones")
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to open it from other devices")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = ap.parse_args(argv)

    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}/"
    print(f"POLARIS Ground Station: {url}  (Ctrl+C oprește serverul)")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, (url,)).start()
    app = create_app(args.link, args.db, args.online_tle)
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
