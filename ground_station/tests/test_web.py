"""Web dashboard: static files, the WebSocket protocol and the hub."""
import asyncio
import json
import re
import threading

import aiohttp
from aiohttp.test_utils import TestServer

from polaris_gs.hub import GroundStation
from polaris_gs.server import WEB, create_app


async def _receive_until(ws, pred, timeout):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    seen = []
    while loop.time() < end:
        try:
            m = await ws.receive(timeout=end - loop.time())
        except asyncio.TimeoutError:
            break
        if m.type != aiohttp.WSMsgType.TEXT:
            break
        msg = json.loads(m.data)
        seen.append(msg)
        if pred(msg):
            return msg, seen
    return None, seen


def test_page_and_every_referenced_file_are_served(tmp_path):
    async def main():
        async with TestServer(create_app("sim", tmp_path / "r.sqlite")) as srv:
            async with aiohttp.ClientSession() as s:
                html = await (await s.get(srv.make_url("/"))).text()
                assert "POLARIS Ground Station" in html
                urls = set(re.findall(r'(?:src|href)="(/static/[^"]+|/assets/[^"]+)"', html))
                for js in WEB.glob("*.js"):
                    urls |= set(re.findall(r'"(/static/[^"]+)"', js.read_text()))
                urls.add("/static/vendor/three/three.module.min.js")
                urls.add("/assets/coastline_110m.json")
                for u in sorted(urls):
                    r = await s.get(srv.make_url(u))
                    assert r.status == 200, u
    asyncio.run(main())


def test_websocket_boot_commands_and_estop(tmp_path):
    async def main():
        async with TestServer(create_app("sim", tmp_path / "r.sqlite")) as srv:
            async with aiohttp.ClientSession() as s:
                async with s.ws_connect(srv.make_url("/ws")) as ws:
                    first, _ = await _receive_until(ws, lambda m: True, 5)
                    assert first["t"] == "hello" and first["link"]["sim"] is True
                    tm, _ = await _receive_until(ws, lambda m: m["t"] == "tm" and m["d"]["mode"] == "WAIT_AOS", 15)
                    d = tm["d"]
                    for k in ("ant_sky_az", "ant_sky_el", "az_rate", "sat_ecef", "sat_alt_km", "_t"):
                        assert k in d
                    got, _ = await _receive_until(ws, lambda m: m["t"] == "passes", 5)
                    assert got["rows"] and got["rows"][0]["sky_diff_s"] < 2.0   # skyfield agrees on AOS
                    xc, _ = await _receive_until(ws, lambda m: m["t"] == "xcheck", 5)
                    assert xc["diff"] < 0.1
                    await ws.send_json({"op": "cmd", "text": "MODE:MANUAL"})
                    ev, _ = await _receive_until(
                        ws, lambda m: m["t"] == "ev" and m["d"]["ev"] == "MODE" and m["d"]["to"] == "MANUAL", 5)
                    assert ev
                    await ws.send_json({"op": "estop", "on": True})
                    ev, _ = await _receive_until(ws, lambda m: m["t"] == "ev" and m["d"]["ev"] == "ESTOP", 5)
                    assert ev
                    await ws.send_json({"op": "estop", "on": False})
                    await ws.send_json({"op": "cmd", "text": "ACK"})
                    ev, _ = await _receive_until(ws, lambda m: m["t"] == "ev" and m["d"]["ev"] == "ACK", 5)
                    assert ev
    asyncio.run(main())


def test_los_is_saved_from_the_link_thread(tmp_path):
    out = []
    hub = GroundStation(out.append, db_path=tmp_path / "r.sqlite")
    los = '{"ev":"LOS","sat":25544,"t_utc":"2026-10-16T03:04:26.9Z","max_err":4.9,"rms_err":2.0,"n":775,"comp":1,"warp":30}'
    t = threading.Thread(target=hub.on_line, args=(los,))   # the sim emits from its own thread
    t.start()
    t.join()
    rows = hub.results()["rows"]
    assert len(rows) == 1 and rows[0]["max_err"] == 4.9 and rows[0]["comp"] == 1
    assert any(m["t"] == "results" for m in out)


def test_vehicle_stream_is_not_logged(tmp_path):
    out = []
    hub = GroundStation(out.append)
    hub.on_line('{"ev":"CMD","cmd":"VEH:1.0,2.0,90.0"}')
    hub.on_line('{"ev":"CMD","cmd":"MODE:DEMO"}')
    assert [m["d"]["cmd"] for m in out if m["t"] == "ev"] == ["MODE:DEMO"]


def _with_checksum(line):
    s = sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line[:68])
    return line[:68] + str(s % 10)


def test_skyfield_check_uses_the_controllers_tle():
    """The controller downloaded a fresher TLE than the stored one (the Wokwi case):
    the station must ask for it and check skyfield against the same elements."""
    import time

    from polaris_gs.core.tle_data import FALLBACK_TLE
    from polaris_gs.link import SimLink

    out = []
    hub = GroundStation(out.append)
    hub.connect("sim")
    try:
        name, l1, l2 = FALLBACK_TLE[25544]
        epoch = float(l1[18:32]) + 0.5                 # a different, valid element set
        new_l1 = _with_checksum(l1[:18] + f"{epoch:14.8f}" + l1[32:])
        deadline = time.time() + 15     # after boot: the station missed the announcement
        while (hub.store.last is None or hub.store.last["mode"] in ("BOOT", "HOMING")) and time.time() < deadline:
            time.sleep(0.1)
        link = hub.link
        assert isinstance(link, SimLink)
        with link._lock:
            assert link.rig.ctl.load_tle(25544, name, new_l1, l2, False, time.time(), False)
        diffs = []
        deadline = time.time() + 20
        while time.time() < deadline:
            time.sleep(0.3)
            hub.tick_slow()
            x = hub.last_xcheck
            if x and x["diff"] is not None:
                diffs.append(x["diff"])
                if hub.xcheck.tles[25544][1] == new_l1:
                    break
        assert hub.xcheck.tles[25544][1] == new_l1, "the station never received the controller's TLE"
        assert diffs[-1] < 0.1
        assert any(m["t"] == "xcheck" and m["diff"] is None for m in out)   # it said "waiting"
    finally:
        hub.stop()
