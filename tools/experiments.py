"""Pointing error experiments for the report.

Runs the Python copy of the firmware (same states and numbers as the ESP32
build, see tests/test_firmware_parity.py) faster than real time, with the
vehicle motion fed as VEH commands, and measures the true pointing error
(antenna boresight vs satellite direction, vehicle attitude applied) while
the controller is in ACQUIRE or TRACK (from AOS to LOS).

usage: python tools/experiments.py [out_dir]   (default docs/results)
writes: experiments.md (tables), experiments.csv, error_*.csv, error_*.png,
        rows in experiments.sqlite
"""
import csv
import math
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from polaris_gs.core import config as C  # noqa: E402
from polaris_gs.core import protocol as P  # noqa: E402
from polaris_gs.sim.runner import DT_MS, SimRig  # noqa: E402
from polaris_gs.store import ResultsDB  # noqa: E402
from polaris_gs.vehicle import VehicleMotion  # noqa: E402

# Passes (fallback TLEs, so the runs are repeatable without internet)
T0_ISS_43 = 1792015503.0          # DEMO picks the ISS pass of 15 Oct 2026 03:44, max el 42.9
T0_ISS_ZENITH = 1786937667.0      # ISS pass of 17 Aug 2026 03:44, max el 89.4 (keyhole)


def run(t0, warp, vehicle, comp, planner=True, seed=1, accel_scale=1.0):
    """One DEMO pass. Returns the list of (pass time s, error deg) in TRACK."""
    saved = (C.AZ_ACCEL_DPS2, C.EL_ACCEL_DPS2)
    C.AZ_ACCEL_DPS2 *= accel_scale
    C.EL_ACCEL_DPS2 *= accel_scale
    events = []
    rig = SimRig(events.append, t0)
    ctl = rig.ctl
    ctl.planner = planner
    motion = VehicleMotion(vehicle, seed=seed)
    ms = 0
    track, los = [], None
    try:
        rig.inp.ms, rig.inp.t_real = 0, t0
        ctl.boot_done(rig.inp)
        booted = False
        while ms < 20 * 60 * 1000:
            ms += DT_MS
            if not booted and ctl.state == "WAIT_AOS":
                ctl.command(f"WARP:{warp}")
                ctl.command(f"COMP:{1 if comp else 0}")
                ctl.command("MODE:DEMO")
                booted = True
            r, p, y = motion.attitude(ms / 1000.0)
            ctl.veh_active, ctl.veh, ctl.veh_ms = True, (r, p, y), ms
            rig.step(ms, t0 + ms / 1000.0)
            if ctl.state in ("ACQUIRE", "TRACK") and ctl.demo:
                track.append((ctl.t_sim, ctl.err))
            if booted and any('"ev":"LOS"' in e for e in events[-3:]):
                los = next(e for e in reversed(events) if '"ev":"LOS"' in e)
                break
    finally:
        C.AZ_ACCEL_DPS2, C.EL_ACCEL_DPS2 = saved
    aos = next((e for e in events if '"ev":"AOS"' in e), None)
    return track, aos, los, events


def stats(track):
    e = sorted(x for _, x in track)
    n = len(e)
    return {
        "n": n,
        "max": e[-1],
        "rms": math.sqrt(sum(x * x for x in e) / n),
        "mean": statistics.fmean(e),
        "p95": e[min(n - 1, int(0.95 * n))],
    }


def plot(path, series, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # validated light palette (dataviz skill): blue, orange, aqua, violet
    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6"]
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=130)
    for (label, track), col in zip(series, colors):
        t0 = track[0][0]
        ax.plot([(t - t0) / 60 for t, _ in track], [e for _, e in track], color=col, lw=1.6, label=label)
    ax.set_xlabel("timp de la începutul urmăririi [min, timp simulat]")
    ax.set_ylabel("eroare de pointare [°]")
    ax.set_title(title, loc="left", fontsize=11)
    ax.grid(alpha=0.25)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, fontsize=9)
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs" / "results")
    out.mkdir(parents=True, exist_ok=True)
    db = ResultsDB(out / "experiments.sqlite")
    cases = [
        # name, t0, warp, vehicle, comp, planner, accel_scale, label
        ("A1", T0_ISS_43, 10, "stationary", True, True, 1.0, "staționar"),
        ("A2", T0_ISS_43, 10, "bumpy", True, True, 1.0, "drum denivelat, cu compensare"),
        ("A3", T0_ISS_43, 10, "bumpy", False, True, 1.0, "drum denivelat, fără compensare"),
        ("A4", T0_ISS_43, 10, "slope", True, True, 1.0, "pantă 8°, cu compensare"),
        ("A5", T0_ISS_43, 10, "slope", False, True, 1.0, "pantă 8°, fără compensare"),
        ("A6", T0_ISS_43, 10, "bumpy", True, True, 3.0, "drum denivelat, cu compensare, accelerație x3"),
        ("B1", T0_ISS_ZENITH, 1, "stationary", True, True, 1.0, "zenit x1, cu planificare keyhole"),
        ("B2", T0_ISS_ZENITH, 1, "stationary", True, False, 1.0, "zenit x1, fără planificare"),
        ("B3", T0_ISS_ZENITH, 10, "stationary", True, True, 1.0, "zenit x10, cu planificare keyhole"),
        ("B4", T0_ISS_ZENITH, 10, "stationary", True, False, 1.0, "zenit x10, fără planificare"),
    ]
    rows, tracks = [], {}
    for name, t0, warp, veh, comp, planner, acc, label in cases:
        track, aos, los, events = run(t0, warp, veh, comp, planner, accel_scale=acc)
        s = stats(track)
        aos_d = P.parse_line(aos)[1] if aos else {}
        rows.append(dict(id=name, label=label, warp=warp, vehicle=veh, comp=comp, planner=planner,
                         accel=acc, aos=aos_d.get("t_utc", ""), **s))
        tracks[name] = track
        with open(out / f"error_{name}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t_sim_unix", "err_deg"])
            w.writerows((f"{t:.1f}", f"{e:.4f}") for t, e in track)
        db.save_experiment(name=f"{name} {label}", sat=25544, aos_utc=aos_d.get("t_utc"),
                           max_el=None, vehicle=veh, comp=int(comp), warp=warp, planner=int(planner),
                           max_err=s["max"], rms_err=s["rms"], p95_err=s["p95"], n=s["n"],
                           extra={"accel_scale": acc})
        print(f"{name:3s} {label:48s} max {s['max']:6.2f}  rms {s['rms']:5.2f}  p95 {s['p95']:5.2f}  n {s['n']}")

    with open(out / "experiments.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    plot(out / "error_compensation.png",
         [("staționar", tracks["A1"]), ("denivelat, cu compensare", tracks["A2"]),
          ("denivelat, fără compensare", tracks["A3"])],
         "Pasaj ISS 15.10.2026 (max 42,9°), DEMO x10")
    plot(out / "error_keyhole.png",
         [("x1, cu planificare", tracks["B1"]), ("x1, fără planificare", tracks["B2"]),
          ("x10, cu planificare", tracks["B3"]), ("x10, fără planificare", tracks["B4"])],
         "Pasaj ISS 17.08.2026 prin zenit (max 89,4°): keyhole")

    md = ["# Rezultatele experimentelor", "",
          "Generat de `tools/experiments.py` (copia Python a firmware-ului, aceleași numere ca ESP32).",
          "Eroarea = unghiul real dintre axa antenei și direcția satelitului, cu înclinarea vehiculului",
          "aplicată, măsurată la 50 Hz de la AOS la LOS (stările ACQUIRE și TRACK). Limite: azimut 40°/s, 120°/s², "
          "elevație 30°/s, 120°/s².", "",
          "| ID | Scenariu | Viteză | Eroare max [°] | RMS [°] | P95 [°] | Eșantioane |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['id']} | {r['label']} | x{r['warp']} | {r['max']:.2f} | {r['rms']:.2f} | "
                  f"{r['p95']:.2f} | {r['n']} |")
    md += ["", "![Compensare](error_compensation.png)", "", "![Keyhole](error_keyhole.png)", ""]
    (out / "experiments.md").write_text("\n".join(md))
    print("written", out / "experiments.md")


if __name__ == "__main__":
    main()
