"""Non-GUI parts of the dashboard: storage, vehicle generator, cross-check."""
import math

from polaris_gs.core import protocol as P
from polaris_gs.crosscheck import CrossCheck
from polaris_gs.sim.runner import run_scenario
from polaris_gs.store import ResultsDB, TelemetryStore
from polaris_gs.vehicle import VehicleMotion

SCEN = "T0 1792015503\n@0 BOOT\n@4000 CMD MODE:DEMO\nEND 30000\n"


def test_results_db_roundtrip(tmp_path):
    db = ResultsDB(tmp_path / "r.sqlite")
    db.save_pass({"sat": 25544, "t_utc": "2026-10-15T03:53:03.0Z", "comp": 1, "warp": 30,
                  "max_err": 1.2, "rms_err": 0.4, "n": 100}, "sim", "bumpy")
    rows = db.passes()
    assert len(rows) == 1 and rows[0][2] == 25544 and rows[0][7] == 1.2


def test_vehicle_generator_ranges_and_repeatable():
    a, b = VehicleMotion("bumpy", seed=3), VehicleMotion("bumpy", seed=3)
    sa = [a.attitude(i * 0.05) for i in range(400)]
    sb = [b.attitude(i * 0.05) for i in range(400)]
    assert sa == sb
    assert max(abs(r) for r, _, _ in sa) < 10 and max(abs(p) for _, p, _ in sa) < 10
    assert VehicleMotion("stationary").attitude(5) == (0.0, 0.0, 90.0)
    r, p, _ = VehicleMotion("slope").attitude(10)
    assert p == -8.0 and r == 2.0


def test_sim_telemetry_parses_and_matches_skyfield():
    store, xc, diffs = TelemetryStore(), CrossCheck(), []
    for line in run_scenario(SCEN):
        kind_d = P.parse_line(line.split(" ", 1)[1])
        if kind_d and kind_d[0] == "telemetry":
            store.add_telemetry(kind_d[1])
            diffs.append(xc.difference(kind_d[1]))
    assert len(store.hist) > 200
    assert any(d["mode"] == "TRACK" for d in store.hist)
    # telemetry is rounded to 0.01 deg, skyfield must agree within 0.1 deg
    assert max(diffs) < 0.1
    assert all(not math.isinf(d["_az_rate"]) for d in store.hist)
