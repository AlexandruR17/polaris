"""Electrical schematic of the physical build (documentation only).

Two sheets, connected by net names (a label with the same name is the same
wire): power, safety and motors; logic, sensors and operator interface.

usage: python tools/schematic.py [out_dir]   (default docs/hardware)
writes schematic_power.svg/png and schematic_logic.svg/png
"""
import pathlib
import sys

import schemdraw
import schemdraw.elements as elm

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

FONT = 11
RED, BLACK, BLUE, ORANGE, GRAY = "#c0392b", "#111111", "#1f5fbf", "#d35400", "#555555"
PURPLE = "#7d3c98"


def ic(d, label, pins, w=3.0, h=None, at=(0, 0), color=BLACK):
    """IC block, label above it. pins: list of (name, side); per side the
    first pin listed is the bottom (or left) one."""
    counts = {s: sum(1 for _, ss in pins if ss == s) for s in "LRTB"}
    if h is None:
        h = max(counts["L"], counts["R"], 2) * 0.6 + 0.4
    blk = d.add(elm.Ic(pins=[elm.IcPin(name=n, side=s) for n, s in pins], edgepadW=0.5,
                       edgepadH=0.5, pinspacing=0.6, w=w, h=h, plblsize=FONT - 2).right().at(at).color(color))
    bb = blk.get_bbox(transform=True)
    d.add(elm.Label().at(((bb.xmin + bb.xmax) / 2, bb.ymax + 0.4)).label(
        label, loc="top", fontsize=FONT + 1, color=color))
    return blk


def net(d, anchor, name, direction="left", length=0.8, color=BLUE):
    """Short stub from a pin with a net name at the end."""
    line = getattr(elm.Line(), direction)(length).at(anchor).color(color)
    d.add(line)
    loc = {"left": "left", "right": "right", "up": "top", "down": "bottom"}[direction]
    d.add(elm.Label().at(line.end).label(name, loc=loc, fontsize=FONT - 1, color=color))
    return line.end


def side(d, el, text, dx=0.45, color=BLACK):
    """Text to the right of a vertical element, centered on it."""
    d.add(elm.Label().at((el.center[0] + dx, el.center[1])).label(text, fontsize=9, halign="left", color=color))


def gnd(d, anchor, direction="down", length=0.5):
    line = d.add(getattr(elm.Line(), direction)(length).at(anchor).color(BLACK))
    d.add(elm.Ground().at(line.end))


def power_sheet(path):
    with schemdraw.Drawing(file=None, show=False) as d:
        d.config(fontsize=FONT, unit=2.0)
        d.add(elm.Label().at((0, 4.2)).label("POLARIS SAT-1 · foaia 1/2 · alimentare, siguranță, motoare",
                                             fontsize=14, halign="left"))
        # 12 V supply, fuse, main switch, +12V node
        src = d.add(elm.SourceV().up().at((0, -1)).color(RED))
        d.add(elm.Label().at((src.center[0] - 0.9, src.center[1])).label("12 V\n5 A", loc="left", color=RED))
        gnd(d, src.start)
        d.add(elm.Line().up(1.0).at(src.end).color(RED))
        d.add(elm.Fuse().right().label("F1 3 A").color(RED))
        sw = d.add(elm.Switch().right().label("S1 pornire").color(RED))
        d.add(elm.Line().right(1.0).color(RED))
        node12 = d.add(elm.Dot().color(RED)).center
        d.add(elm.Label().at(node12).label("+12V", loc="top", color=RED))
        # buck 12 -> 5 V under the node
        buck = ic(d, "coborâtor LM2596\n12 V → 5 V", [("IN", "L"), ("GND", "B"), ("OUT", "R")],
                  w=2.6, h=1.4, at=(node12[0] + 0.8, node12[1] - 4.0))
        d.add(elm.Line().at(node12).toy(buck.IN).color(RED))
        d.add(elm.Line().tox(buck.IN).color(RED))
        gnd(d, buck.GND)
        net(d, buck.OUT, "+5V (ESP32 5V, LCD)", "right", 1.0, RED)
        _ = sw

        # E-STOP (NC) in series with the relay coil: pressing it de-energises
        # the coil without any software, the NO contact opens VMOT.
        x0, y0 = 13.0, 2.6
        d.add(elm.Label().at((x0, y0 + 1.6)).label("Lanț de siguranță (hardware)", fontsize=12, halign="left"))
        p5 = d.add(elm.Line().right(0.8).at((x0, y0)).color(RED))
        d.add(elm.Label().at(p5.start).label("+5V", loc="left", color=RED))
        es = d.add(elm.Button(nc=True).right().color(RED))
        d.add(elm.Label().at((es.center[0], es.center[1] - 0.7)).label("E-STOP (NC, cu reținere)",
                                                                     fontsize=9, color=RED))
        d.add(elm.Line().right(1.0).color(RED))
        top = d.add(elm.Dot()).center
        coil = d.add(elm.Inductor2().down().at(top))
        d.add(elm.Label().at((coil.center[0] - 1.0, coil.center[1])).label("bobină K1", loc="left", fontsize=9))
        bot = d.add(elm.Dot()).center
        d.add(elm.Line().right(1.4).at(top))
        dio = d.add(elm.Diode().down().reverse().label("D1 1N4148", loc="right", fontsize=9))
        d.add(elm.Line().tox(bot))
        d.add(elm.Line().down(1.0).at(bot))
        q = d.add(elm.BjtNpn(circle=True).right().anchor("collector").label("Q1 BC547", loc="right"))
        gnd(d, q.emitter)
        rb = d.add(elm.Resistor().left().at(q.base).label("1 kΩ", loc="bottom"))
        d.add(elm.Label().at(rb.end).label("RELAY (GPIO13)", loc="left", color=BLUE))
        k = d.add(elm.Switch(action="close").right().at((x0, y0 - 6.0)).label("contact K1 (NO)").color(RED))
        d.add(elm.Label().at(k.start).label("+12V", loc="left", color=RED))
        d.add(elm.Line().right(0.8).color(RED))
        d.add(elm.Label().label("VMOT", loc="right", color=RED))
        d.add(elm.Label().at((x0 - 0.8, y0 - 7.4)).label(
            "E-STOP are și un contact auxiliar NO spre GPIO12 (foaia 2): firmware-ul vede apăsarea,\n"
            "dar VMOT se taie prin releu chiar dacă ESP32 nu răspunde (oprire de categoria 0).",
            fontsize=9, halign="left", color=GRAY))
        _ = dio

        # two A4988 drivers, each with its motor on the right
        drv_right = [("GND", "R"), ("VDD", "R"), ("1B", "R"), ("1A", "R"), ("2A", "R"), ("2B", "R"),
                     ("GND2", "R"), ("VMOT", "R")]
        drv_left = [("DIR", "L"), ("STEP", "L"), ("SLEEP", "L"), ("RESET", "L"), ("MS3", "L"),
                    ("MS2", "L"), ("MS1", "L"), ("ENABLE", "L")]
        for i, (axis, y) in enumerate((("AZ", -11.0), ("EL", -19.0))):
            xd = 3.0
            drv = ic(d, f"A4988 #{i + 1} · axa {axis}", drv_left + drv_right, w=2.8, at=(xd, y))
            net(d, drv.ENABLE, f"{axis}_EN", "left", 1.2)
            net(d, drv.STEP, f"{axis}_STEP", "left", 1.2)
            net(d, drv.DIR, f"{axis}_DIR", "left", 1.2)
            for pn in ("MS1", "MS2", "MS3"):
                net(d, getattr(drv, pn), "+3V3", "left", 0.8, RED)
            d.add(elm.Line().at(drv.RESET).left(0.4).color(RED))
            d.add(elm.Line().toy(drv.SLEEP).color(RED))
            d.add(elm.Line().tox(drv.SLEEP).color(RED))
            net(d, drv.VDD, "+3V3", "right", 0.8, RED)
            for pn in ("GND", "GND2"):
                g = d.add(elm.Line().right(0.8).at(getattr(drv, pn)))
                d.add(elm.Label().at(g.end).label("GND", loc="right", fontsize=9))
            # VMOT with the 100 uF bulk capacitor right at the driver
            v = d.add(elm.Line().right(0.9).at(drv.VMOT).color(RED))
            d.add(elm.Dot().color(RED))
            d.add(elm.Line().right(2.8).color(RED))
            d.add(elm.Label().label("VMOT", loc="right", color=RED))
            d.add(elm.Line().up(1.2).at(v.end).color(RED))
            d.add(elm.Capacitor(polar=True).right().label("100 µF / 35 V", loc="top", fontsize=9))
            d.add(elm.Line().down(0.2))
            d.add(elm.Ground())
            # motor block, its first pin level with 1B
            mot = ic(d, f"M{i + 1} NEMA 17 + reductor 5:1",
                     [("B−", "L"), ("B+", "L"), ("A+", "L"), ("A−", "L")],
                     w=2.6, at=(xd + 10.0, y + 1.2), color=PURPLE)
            for dp, mp in (("1B", "B−"), ("1A", "B+"), ("2A", "A+"), ("2B", "A−")):
                a, b = getattr(drv, dp), mot.absanchors[mp]
                d.add(elm.Line().at(a).right(5.0).color(PURPLE))
                d.add(elm.Line().toy(b).color(PURPLE))
                d.add(elm.Line().tox(b).color(PURPLE))
        d.save(str(path) + ".svg")
        d.save(str(path) + ".png", dpi=150)


def logic_sheet(path):
    with schemdraw.Drawing(file=None, show=False) as d:
        d.config(fontsize=FONT, unit=2.0)
        d.add(elm.Label().at((0, 7.6)).label(
            "POLARIS SAT-1 · foaia 2/2 · ESP32, senzori, interfață operator", fontsize=14, halign="left"))
        esp = ic(d, "ESP32\nDevKitC V4",
                 [("3V3", "L"), ("VP/36", "L"), ("VN/39", "L"), ("34", "L"), ("35", "L"), ("32", "L"),
                  ("33", "L"), ("25", "L"), ("26", "L"), ("27", "L"), ("14", "L"), ("12", "L"),
                  ("13", "L"), ("GND", "L"), ("5V", "L"),
                  ("23", "R"), ("22", "R"), ("21", "R"), ("19", "R"), ("18", "R"), ("5", "R"),
                  ("17", "R"), ("16", "R"), ("4", "R"), ("2", "R"), ("15", "R"), ("GND ", "R")],
                 w=3.2, at=(0, -4.5))
        left = {"3V3": "+3V3", "VP/36": "POT", "VN/39": "ENC_CLK", "34": "ENC_DT", "35": "ENC_SW",
                "32": "AZ_DIR", "33": "AZ_STEP", "25": "AZ_EN", "26": "EL_DIR", "27": "EL_STEP",
                "14": "EL_EN", "12": "ESTOP_AUX", "13": "RELAY", "GND": "GND", "5V": "+5V"}
        for p, n in left.items():
            net(d, getattr(esp, p.replace("/", "_")) if hasattr(esp, p.replace("/", "_")) else esp.absanchors[p],
                n, "left", 1.0, RED if n.startswith("+") else (BLACK if n == "GND" else BLUE))
        right = {"23": "SDA", "22": "SCL", "21": "LIM_AZ", "19": "LIM_EL", "18": "BTN_MOD",
                 "5": "BTN_HOME", "17": "BTN_STOW", "16": "LED_G", "4": "LED_Y", "2": "LED_R",
                 "15": "BUZZER", "GND ": "GND"}
        for p, n in right.items():
            net(d, esp.absanchors[p], n, "right", 1.0, BLACK if n == "GND" else BLUE)

        # I2C bus with pull-ups
        x, y = 9.5, 5.6
        d.add(elm.Label().at((x - 1.6, y - 2.9)).label("Magistrala I2C (3,3 V)", fontsize=12, halign="left"))
        for i, n in enumerate(("SDA", "SCL")):
            r = d.add(elm.Resistor().up().at((x - 0.8 + 1.8 * i, y - 1.6)))
            side(d, r, "4,7 kΩ")
            d.add(elm.Label().at(r.end).label("+3V3", loc="top", color=RED))
            d.add(elm.Label().at(r.start).label(n, loc="bottom", color=BLUE))
        devs = [("MPU6050 · 0x68", 0, 0, BLACK), ("SSD1306 OLED · 0x3C", 1, 0, BLACK),
                ("LCD 2004 + PCF8574 · 0x27 (5 V*)", 2, 0, BLACK), ("TCA9548A · 0x70 (opțional)", 0, 1, GRAY),
                ("AS5600 axa AZ (opțional, canal 0)", 1, 1, GRAY), ("AS5600 axa EL (opțional, canal 1)", 2, 1, GRAY)]
        for name, cx, cy, colr in devs:
            blk = ic(d, name, [("VCC", "L"), ("GND", "L"), ("SDA", "R"), ("SCL", "R")], w=2.4, h=1.6,
                     at=(x + 5.0 + 7.0 * cx, y - 1.4 - 4.0 * cy), color=colr)
            net(d, blk.VCC, "+5V" if "LCD" in name else "+3V3", "left", 0.6, RED)
            net(d, blk.GND, "GND", "left", 0.6, BLACK)
            sda, scl = ("SDA", "SCL") if "AS5600" not in name else (f"SD{cx - 1}", f"SC{cx - 1}")
            net(d, blk.SDA, sda, "right", 0.6, BLUE if colr == BLACK or "TCA" in name else GRAY)
            net(d, blk.SCL, scl, "right", 0.6, BLUE if colr == BLACK or "TCA" in name else GRAY)
        d.add(elm.Label().at((x - 0.6, y - 7.6)).label(
            "* LCD-ul cere 5 V: scoateți pull-up-urile de 5 V de pe modulul PCF8574 sau folosiți un translator de nivel\n"
            "  (ex. BSS138), ca SDA/SCL să rămână la 3,3 V. Cele două AS5600 au aceeași adresă (0x36), de aceea trec\n"
            "  prin TCA9548A (canalele SD0/SC0 și SD1/SC1); ele permit buclă închisă de poziție pe hardware real.",
            fontsize=9, halign="left", color=GRAY))

        # operator inputs: each switch pulls its GPIO to GND
        x2, y2 = 9.5, -5.6
        d.add(elm.Label().at((x2 - 0.6, y2 + 2.0)).label("Interfață operator și limitatoare", fontsize=12,
                                                        halign="left"))
        sws = [("BTN_MOD", "MOD", False), ("BTN_HOME", "HOME", False), ("BTN_STOW", "STOW", False),
               ("ESTOP_AUX", "E-STOP\naux (NO)", False), ("LIM_AZ", "limitator\nAZ (NC)", True),
               ("LIM_EL", "limitator\nEL (NC)", True)]
        for col, (n, lab, nc) in enumerate(sws):
            b = d.add(elm.Button(nc=nc).down().at((x2 + 2.6 * col, y2)))
            side(d, b, lab)
            d.add(elm.Label().at((b.start[0], b.start[1] + 0.3)).label(n, loc="top", color=BLUE, fontsize=9))
            d.add(elm.Ground().at(b.end))
        d.add(elm.Label().at((x2 - 0.6, y2 - 2.9)).label(
            "Butoane și limitatoare: pull-up intern (INPUT_PULLUP). Limitator NC: deschis = atins sau fir rupt.",
            fontsize=9, halign="left", color=GRAY))
        # KY-040 encoder, its SW pull-up and the speed potentiometer
        enc = ic(d, "KY-040", [("CLK", "L"), ("DT", "L"), ("SW", "L"), ("+", "R"), ("GND", "R")],
                 w=2.0, h=2.0, at=(x2 + 18.0, y2 - 1.6))
        for pn, n in (("CLK", "ENC_CLK"), ("DT", "ENC_DT"), ("SW", "ENC_SW")):
            net(d, getattr(enc, pn), n, "left", 0.8)
        net(d, enc.absanchors["+"], "+3V3", "right", 0.6, RED)
        net(d, enc.GND, "GND", "right", 0.6, BLACK)

        # outputs: LEDs with series resistors, buzzer
        y3 = y2 - 4.4
        for i, (n, colr, lab) in enumerate((("LED_G", "green", "verde\nURMĂRIRE"),
                                           ("LED_Y", "#d4a017", "galben\nAȘTEPTARE"),
                                           ("LED_R", "red", "roșu\nEROARE"))):
            r = d.add(elm.Resistor().down().at((x2 + 2.6 * i, y3)))
            side(d, r, "220 Ω")
            d.add(elm.Label().at((r.start[0], r.start[1] + 0.3)).label(n, loc="top", color=BLUE, fontsize=9))
            led = d.add(elm.LED().down().color(colr))
            side(d, led, lab, dx=0.8)
            d.add(elm.Ground())
        bz = d.add(elm.Speaker().right().at((x2 + 8.6, y3 - 1.0)))
        d.add(elm.Label().at((bz.in1[0] + 0.6, bz.in1[1] - 1.4)).label("buzzer piezo activ", fontsize=9))
        d.add(elm.Label().at(bz.in1).label("BUZZER", loc="left", color=BLUE, fontsize=9))
        d.add(elm.Ground().at(bz.in2))
        rsw = d.add(elm.Resistor().up().at((x2 + 14.0, y3 - 2.0)))
        side(d, rsw, "10 kΩ (GPIO35 nu are\npull-up intern)")
        d.add(elm.Label().at((rsw.start[0], rsw.start[1] - 0.3)).label("ENC_SW", loc="bottom", color=BLUE, fontsize=9))
        d.add(elm.Label().at(rsw.end).label("+3V3", loc="top", color=RED, fontsize=9))
        pot = d.add(elm.Potentiometer().up().at((x2 + 19.5, y3 - 2.0)))
        side(d, pot, "10 kΩ\nviteză manuală", dx=0.9)
        d.add(elm.Label().at(pot.end).label("+3V3", loc="top", color=RED, fontsize=9))
        d.add(elm.Ground().at(pot.start))
        d.add(elm.Line().left(0.8).at(pot.tap).color(BLUE))
        d.add(elm.Label().label("POT", loc="left", color=BLUE, fontsize=9))
        d.save(str(path) + ".svg")
        d.save(str(path) + ".png", dpi=150)


def main():
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs" / "hardware")
    out.mkdir(parents=True, exist_ok=True)
    power_sheet(out / "schematic_power")
    logic_sheet(out / "schematic_logic")
    print("written", out)


if __name__ == "__main__":
    main()
