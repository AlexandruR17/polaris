import json

import pytest

from polaris_gs.core import protocol as P


@pytest.mark.parametrize("line,name,args", [
    ("SAT:25544", "SAT", (25544,)),
    ("sat:33591\r\n", "SAT", (33591,)),
    ("MODE:demo", "MODE", ("DEMO",)),
    ("WARP:30", "WARP", (30,)),
    ("VEH:1.5,-2.25,90", "VEH", (1.5, -2.25, 90.0)),
    ("VEH:OFF", "VEH", ()),
    ("JOG:az,-12.5", "JOG", ("AZ", -12.5)),
    ("HOME", "HOME", ()),
    ("STOW", "STOW", ()),
    ("ACK", "ACK", ()),
    ("COMP:0", "COMP", (False,)),
])
def test_parse_valid(line, name, args):
    c = P.parse_command(line)
    assert c.name == name and c.args == args


@pytest.mark.parametrize("line", [
    "", "SAT:", "SAT:ISS", "MODE:FAST", "WARP:7", "VEH:1,2", "VEH:a,b,c", "VEH:50,0,0",
    "JOG:XY,5", "JOG:AZ,500", "HOME:1", "FOO", "COMP:2", "VEH:nan,0,0",
])
def test_parse_invalid(line):
    with pytest.raises(ValueError):
        P.parse_command(line)


def test_format_roundtrip():
    s = P.format_command("VEH", 1.0, -2.0, 90.0)
    assert s == "VEH:1.00,-2.00,90.00\n"
    assert P.parse_command(s).args == (1.0, -2.0, 90.0)
    assert P.format_command("COMP", True) == "COMP:1\n"


def test_parse_telemetry_and_events():
    t = {k: 0 for k in P.TELEMETRY_KEYS}
    t.update(t_utc="2026-10-14T22:05:03.1Z", next_aos=None, next_los=None, mode="IDLE")
    kind, d = P.parse_line(json.dumps(t))
    assert kind == "telemetry"
    assert d["t_utc_unix"] == pytest.approx(1792015503.1)
    kind, d = P.parse_line('{"ev":"AOS","sat":25544}')
    assert kind == "event" and d["ev"] == "AOS"
    assert P.parse_line("POLARIS boot text") is None
    assert P.parse_line("{broken") is None
    assert P.parse_line('{"a":1}') is None


def test_iso_roundtrip():
    for t in (0.0, 1792015503.1, 1792015503.95):
        assert P.parse_iso_utc(P.iso_utc(t)) == pytest.approx(int(t * 10) / 10)
