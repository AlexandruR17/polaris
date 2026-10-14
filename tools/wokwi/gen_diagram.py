"""Generate firmware/diagram.json for POLARIS SAT-1.

Layout: the ESP32 lies horizontally (rotate 90), so its two pin rows face up
and down. Everything wired to the upper pin row (power switching, the two
axes, the manual knobs) sits above the board, in the same left-to-right
order as the pins; the operator panel and the sensors sit below. Each
signal wire makes at most one horizontal jog at its own level, so signal
bundles never cross. Supply (red) and ground (black) run on lanes along
the edges of each group; a few of them cross signal wires at right angles.

usage: python tools/wokwi/gen_diagram.py [out.json]
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from geometry import Part  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]

# wire colours by function (same table in the legend and in README)
COLORS = {
    "pwr": ("red", "alimentare logică 3V3"),
    "vmot": ("#b91c1c", "alimentare motoare (prin releu)"),
    "gnd": ("black", "masă (GND)"),
    "motor": ("orange", "STEP / DIR / ENABLE"),
    "coil": ("purple", "bobine motor"),
    "safety": ("magenta", "E-STOP și releu"),
    "manual": ("teal", "encoder și potențiometru"),
    "i2c": ("blue", "magistrala I2C"),
    "limit": ("green", "limitatoare de cursă"),
    "panel": ("#d4a017", "butoane, LED-uri, buzzer"),
}
C = {k: v[0] for k, v in COLORS.items()}

parts = {}
wires = []


def add(p):
    parts[p.id] = p
    return p


def align(p, pin, x=None, y=None):
    px, py = p.pin(pin)
    if x is not None:
        p.left += x - px
    if y is not None:
        p.top += y - py
    return p


def P(ref):
    pid, pin = ref.split(":", 1)
    return parts[pid].pin(pin)


def X(ref):
    return P(ref)[0]


def Y(ref):
    return P(ref)[1]


def wire(a, b, kind, via=()):
    """via: absolute moves from the source pin, ('x', value) or ('y', value).
    The last leg to the target must be straight."""
    x, y = P(a)
    tx, ty = P(b)
    instr = []
    for axis, v in via:
        if axis == "x":
            instr.append("h%g" % round(v - x, 2))
            x = v
        else:
            instr.append("v%g" % round(v - y, 2))
            y = v
    if abs(x - tx) > 0.6 and abs(y - ty) > 0.6:
        raise ValueError(f"{a} -> {b}: last leg not straight ({x:.1f},{y:.1f}) -> ({tx:.1f},{ty:.1f})")
    wires.append([a, b, C[kind], instr])


def label(pid, x, y, s, size=15, color="#111827"):
    add(Part(pid, "wokwi-text", x, y, 0, {"text": s, "fontSize": str(size), "color": color}))


# ------------------------------------------------------------------ board
CX, CY = 900.0, 640.0
esp = add(Part.place_center("esp", "board-esp32-devkit-c-v4", CX, CY, 90))
TOP = Y("esp:3V3")       # upper pin row (left side of the board)
BOT = Y("esp:GND.2")     # lower pin row (right side of the board)


def ex(pin):
    return X(f"esp:{pin}")


# ================================================================== upper band
DRV_Y = 470.0                                  # control pin row of both drivers
J = [DRV_Y + 18 + 10 * i for i in range(8)]   # jog levels, top to bottom
assert J[-1] < TOP - 12

# --- elevation axis: STEP/DIR straight above GPIO27/26
drv_el = add(Part.place_center("drv_el", "wokwi-a4988", 0, 0, 270))
align(drv_el, "STEP", x=ex("27"), y=DRV_Y)
mot_el = add(Part("mot_el", "wokwi-stepper-motor", 0, 0, 0,
                  {"size": "17", "arrow": "#0ea5e9", "display": "angle"}))
align(mot_el, "A-", x=X("drv_el:2B"), y=Y("drv_el:2B") - 44)

# --- azimuth axis, right of the elevation motor
mot_az = add(Part("mot_az", "wokwi-stepper-motor", 0, 0, 0,
                  {"size": "17", "arrow": "#f97316", "display": "angle"}))
mot_az.left, mot_az.top = mot_el.bbox()[2] + 46, mot_el.top
drv_az = add(Part.place_center("drv_az", "wokwi-a4988", 0, 0, 270))
align(drv_az, "2B", x=X("mot_az:A-"), y=Y("drv_el:2B"))
GAP_X = (mot_el.bbox()[2] + mot_az.bbox()[0]) / 2

# --- manual knobs, right of the azimuth motor
enc = add(Part("enc", "wokwi-ky-040", 0, 0, 90))
align(enc, "GND", x=mot_az.bbox()[2] + 80, y=DRV_Y - 40)
pot = add(Part("pot", "wokwi-potentiometer", 0, 0, 0, {"value": "2048"}))
align(pot, "GND", x=X("enc:CLK") + 46, y=Y("enc:CLK"))
r_sw = add(Part.place_center("r_sw", "wokwi-resistor", 0, 0, 90, {"value": "10000"}))
align(r_sw, "2", x=X("enc:GND") - 34, y=Y("enc:GND") - 30)

# --- motor power switching (relay, header towards the board) and E-STOP
estop = add(Part("estop", "wokwi-pushbutton", 0, 0, 90,
                 {"color": "red", "label": "E-STOP", "bounce": "0", "key": "e"}))
align(estop, "1.r", x=mot_el.bbox()[0] - 50, y=DRV_Y - 30)
relay = add(Part("relay", "wokwi-relay-module", 0, 0, 180, {"transistor": "pnp"}))
align(relay, "IN", x=estop.bbox()[0] - 70, y=DRV_Y - 80)
led_pwr = add(Part("led_pwr", "wokwi-led", 0, 0, 0, {"color": "blue", "label": "MOTOARE"}))
align(led_pwr, "A", x=relay.bbox()[0] - 40, y=Y("relay:NO") + 40)
r_pwr = add(Part.place_center("r_pwr", "wokwi-resistor", 0, 0, 90, {"value": "1000"}))
align(r_pwr, "1", x=X("led_pwr:C"), y=Y("led_pwr:C") + 16)

# ================================================================== lower band
LOW = BOT + 150                                # top pin row of the lower parts
K = [BOT + 16 + 10 * i for i in range(12)]     # jog levels below the board
GND_LANE = LOW + 120                           # panel ground lane

buz = add(Part("buzzer", "wokwi-buzzer", 0, 0, 0, {"volume": "0.1"}))
leds = [(add(Part(n, "wokwi-led", 0, 0, 0, {"color": c, "label": t})), pin)
        for n, pin, c, t in (("led_r", "2", "red", "EROARE"), ("led_y", "4", "yellow", "AȘTEPT."),
                             ("led_g", "16", "green", "URMĂRIRE"))]
res = {led.id: add(Part.place_center("r_" + led.id[4:], "wokwi-resistor", 0, 0, 90, {"value": "220"}))
       for led, _ in leds}
buttons = [(add(Part(n, "wokwi-pushbutton", 0, 0, 90,
                     {"color": c, "label": t, "bounce": "0", "key": k})), pin)
           for n, pin, c, t, k in (("btn_stow", "17", "blue", "STOW", "s"),
                                   ("btn_home", "5", "white", "HOME", "h"),
                                   ("btn_mode", "18", "green", "MOD", "m"))]
lim_el = add(Part("lim_el", "wokwi-slide-switch", 0, 0, 180, {"bounce": "0"}))
lim_az = add(Part("lim_az", "wokwi-slide-switch", 0, 0, 180, {"bounce": "0"}))
imu = add(Part("imu", "wokwi-mpu6050", 0, 0, 0))
oled = add(Part("oled", "board-ssd1306", 0, 0, 0))
lcd = add(Part("lcd", "wokwi-lcd2004", 0, 0, 0, {"pins": "i2c"}))

# operator panel: LIM_EL at GPIO19, then buttons, LEDs and buzzer to the left
align(lim_el, "2", x=ex("19") - 22, y=LOW)
x = lim_el.bbox()[0] - 26
for b, pin in reversed(buttons):
    align(b, "1.l", x=0, y=LOW)
    b.left += x - b.bbox()[2]
    x = b.bbox()[0] - 22
for led, pin in reversed(leds):
    align(led, "A", x=0, y=LOW + 40)
    led.left += x - led.bbox()[2] - 8
    align(res[led.id], "1", x=X(f"{led.id}:C"), y=Y(f"{led.id}:C") + 14)
    x = led.bbox()[0] - 16
align(buz, "2", x=0, y=LOW + 80)
buz.left += x - buz.bbox()[2] - 18

# sensors right of GND.3: LIM_AZ, MPU6050, then the displays on the same bus
align(lim_az, "2", x=ex("21") + 26, y=LOW)
align(imu, "SDA", x=lim_az.bbox()[2] + 70, y=LOW)
align(oled, "GND", x=imu.bbox()[2] + 90, y=LOW)
lcd.left = oled.bbox()[2] + 60
align(lcd, "GND", y=LOW + 24)

# ================================================================== upper wires
# elevation driver: STEP and DIR straight down, ENABLE jogs right at the top level
wire("drv_el:STEP", "esp:27", "motor")
wire("drv_el:DIR", "esp:26", "motor")
wire("drv_el:ENABLE", "esp:14", "motor", [("y", J[0]), ("x", ex("14"))])
# azimuth driver and manual knobs: one staircase to the left, rightmost lowest
wire("drv_az:ENABLE", "esp:25", "motor", [("y", J[0]), ("x", ex("25"))])
wire("drv_az:STEP", "esp:33", "motor", [("y", J[1]), ("x", ex("33"))])
wire("drv_az:DIR", "esp:32", "motor", [("y", J[2]), ("x", ex("32"))])
wire("enc:SW", "esp:35", "manual", [("y", J[3]), ("x", ex("35"))])
wire("enc:DT", "esp:34", "manual", [("y", J[4]), ("x", ex("34"))])
wire("enc:CLK", "esp:VN", "manual", [("y", J[5]), ("x", ex("VN"))])
wire("pot:SIG", "esp:VP", "manual", [("y", J[6]), ("x", ex("VP"))])
# safety staircase to the right (under ENABLE of the elevation driver)
wire("estop:1.r", "esp:12", "safety", [("y", J[1]), ("x", ex("12"))])
wire("estop:2.r", "esp:GND.1", "gnd", [("y", J[2]), ("x", ex("GND.1"))])
wire("relay:IN", "esp:13", "safety", [("x", X("relay:IN") + 30), ("y", J[3]), ("x", ex("13"))])
wire("relay:GND", "esp:GND.1", "gnd", [("x", X("relay:GND") + 22), ("y", J[5]), ("x", ex("GND.1"))])
wire("relay:VCC", "esp:5V", "vmot", [("x", X("relay:VCC") + 14), ("y", J[4]), ("x", ex("5V"))])
wire("relay:COM", "relay:VCC", "vmot", [("x", X("relay:COM") - 12), ("y", relay.bbox()[3] + 10),
                                        ("x", X("relay:VCC") + 6), ("y", Y("relay:VCC")),
                                        ("x", X("relay:VCC"))])

for d, m in (("drv_el", "mot_el"), ("drv_az", "mot_az")):
    # 1/16 microstepping: MS1..MS3 high; RESET and SLEEP high as well
    wire(f"{d}:MS1", f"{d}:MS2", "pwr")
    wire(f"{d}:MS2", f"{d}:MS3", "pwr")
    wire(f"{d}:MS3", f"{d}:RESET", "pwr")
    wire(f"{d}:RESET", f"{d}:SLEEP", "pwr")
    # chain to VDD around the right end of the driver
    wire(f"{d}:SLEEP", f"{d}:VDD", "pwr",
         [("y", Y(f"{d}:SLEEP") + 7), ("x", X(f"{d}:DIR") + 12), ("y", Y(f"{d}:VDD") - 9),
          ("x", X(f"{d}:VDD"))])
    # coils straight up into the motor
    for drv_pin, mot_pin in (("2B", "A-"), ("2A", "A+"), ("1A", "B+"), ("1B", "B-")):
        wire(f"{d}:{drv_pin}", f"{m}:{mot_pin}", "coil")

# supply lanes above the motors: 3V3 (lowest), GND, VMOT (highest)
L3 = mot_el.top - 22
LG = mot_el.top - 38
LV = mot_el.top - 54
XR = pot.bbox()[2] + 36                    # right riser: 3V3 up, GND down to GND.2
XRG = XR + 14
XL = led_pwr.bbox()[0] - 30                # left riser for the LED ground
AZR = mot_az.bbox()[2] + 14                # drop right of the azimuth motor

# 3V3: board right end -> right riser -> lane -> both drivers; knobs on the way
wire("esp:3V3", "pot:VCC", "pwr", [("y", TOP - 8), ("x", XR), ("y", Y("pot:VCC") + 12),
                                   ("x", X("pot:VCC"))])
wire("pot:VCC", "drv_az:VDD", "pwr", [("y", Y("pot:VCC") + 12), ("x", XR), ("y", L3),
                                      ("x", AZR), ("y", Y("drv_az:VDD") - 18), ("x", X("drv_az:VDD"))])
wire("drv_az:VDD", "drv_el:VDD", "pwr", [("y", Y("drv_az:VDD") - 18), ("x", AZR), ("y", L3),
                                         ("x", GAP_X - 12), ("y", Y("drv_el:VDD") - 18),
                                         ("x", X("drv_el:VDD"))])
wire("r_sw:1", "drv_az:VDD", "pwr", [("y", L3), ("x", AZR), ("y", Y("drv_az:VDD") - 18),
                                     ("x", X("drv_az:VDD"))])
wire("enc:VCC", "r_sw:1", "pwr", [("y", Y("enc:VCC") + 8), ("x", X("r_sw:1") + 14),
                                  ("y", Y("r_sw:1") - 10), ("x", X("r_sw:1"))])
wire("r_sw:2", "enc:SW", "pwr", [("y", Y("enc:SW") + 4), ("x", X("enc:SW"))])

# ground lane: LED, drivers, knobs; down the right riser to GND.2
wire("drv_az:GND", "enc:GND", "gnd", [("y", Y("drv_az:GND") - 10), ("x", AZR + 12),
                                      ("y", Y("enc:GND") + 16), ("x", X("enc:GND"))])
wire("enc:GND", "pot:GND", "gnd", [("y", Y("enc:GND") + 16), ("x", X("pot:GND") - 10),
                                   ("y", Y("pot:GND") + 6), ("x", X("pot:GND"))])
wire("drv_az:GND", "drv_el:GND", "gnd", [("y", Y("drv_az:GND") - 10), ("x", AZR + 12),
                                         ("y", LG), ("x", GAP_X), ("y", Y("drv_el:GND") - 10),
                                         ("x", X("drv_el:GND"))])
wire("r_pwr:2", "drv_el:GND", "gnd", [("y", Y("r_pwr:2") + 8), ("x", XL), ("y", LG), ("x", GAP_X),
                                      ("y", Y("drv_el:GND") - 10), ("x", X("drv_el:GND"))])
wire("drv_az:GND", "esp:GND.2", "gnd", [("y", Y("drv_az:GND") - 10), ("x", AZR + 12), ("y", LG),
                                        ("x", XRG), ("y", BOT + 9), ("x", ex("GND.2"))])
wire("led_pwr:C", "r_pwr:1", "gnd")

# switched motor supply: relay NO -> VMOT of both drivers, plus the LED
wire("relay:NO", "drv_el:VMOT", "vmot", [("x", X("relay:NO") - 16), ("y", LV),
                                         ("x", X("drv_el:VMOT") - 48), ("y", Y("drv_el:VMOT") - 10),
                                         ("x", X("drv_el:VMOT"))])
wire("drv_el:VMOT", "drv_az:VMOT", "vmot", [("y", Y("drv_el:VMOT") - 10), ("x", X("drv_el:VMOT") - 48),
                                            ("y", LV), ("x", GAP_X + 12), ("y", Y("drv_az:VMOT") - 10),
                                            ("x", X("drv_az:VMOT"))])
wire("relay:NO", "led_pwr:A", "vmot", [("x", X("relay:NO") - 16), ("y", Y("led_pwr:A") + 10),
                                       ("x", X("led_pwr:A"))])

# ================================================================== lower wires
# operator panel: staircase to the left, the rightmost wire turns highest
wire("lim_el:2", "esp:19", "limit", [("y", K[0]), ("x", ex("19"))])
wire("btn_mode:1.l", "esp:18", "panel", [("y", K[1]), ("x", ex("18"))])
wire("btn_home:1.l", "esp:5", "panel", [("y", K[2]), ("x", ex("5"))])
wire("btn_stow:1.l", "esp:17", "panel", [("y", K[3]), ("x", ex("17"))])
for (led, pin), k in zip(reversed(leds), (K[4], K[5], K[6])):
    wire(f"{led.id}:A", f"esp:{pin}", "panel", [("x", X(f"{led.id}:A") + 12), ("y", k), ("x", ex(pin))])
wire("buzzer:2", "esp:15", "panel", [("x", X("buzzer:2") + 26), ("y", K[7]), ("x", ex("15"))])

# panel ground lane, fed straight down from GND.3
wire("esp:GND.3", "lim_el:1", "gnd", [("y", GND_LANE), ("x", X("lim_el:1") + 14), ("y", Y("lim_el:1") - 8),
                                      ("x", X("lim_el:1"))])
for b, _ in buttons:
    wire(f"{b.id}:2.r", "esp:GND.3", "gnd", [("y", GND_LANE), ("x", ex("GND.3"))])
for led, _ in leds:
    wire(f"r_{led.id[4:]}:2", "esp:GND.3", "gnd", [("y", GND_LANE), ("x", ex("GND.3"))])
wire("buzzer:1", "esp:GND.3", "gnd", [("y", GND_LANE), ("x", ex("GND.3"))])

# sensors: staircase to the right, the leftmost wire lowest
wire("lim_az:2", "esp:21", "limit", [("y", K[3]), ("x", ex("21"))])
wire("imu:SDA", "esp:23", "i2c", [("y", K[1]), ("x", ex("23"))])
wire("imu:SCL", "esp:22", "i2c", [("y", K[2]), ("x", ex("22"))])
wire("lim_az:1", "esp:GND.2", "gnd", [("y", Y("lim_az:1") - 12), ("x", XRG - 8), ("y", BOT + 9),
                                      ("x", ex("GND.2"))])
# displays on the same bus (SDA upper lane, SCL lower lane)
wire("oled:SDA", "imu:SDA", "i2c", [("y", K[1]), ("x", X("imu:SDA"))])
wire("oled:SCL", "imu:SCL", "i2c", [("y", K[2]), ("x", X("imu:SCL"))])
wire("lcd:SDA", "oled:SDA", "i2c", [("x", X("lcd:SDA") - 20), ("y", K[1]), ("x", X("oled:SDA"))])
wire("lcd:SCL", "oled:SCL", "i2c", [("x", X("lcd:SCL") - 30), ("y", K[2]), ("x", X("oled:SCL"))])
# sensor supply lanes just above the devices
PS3 = LOW - 26
PSG = LOW - 16
wire("imu:VCC", "oled:VCC", "pwr", [("y", PS3), ("x", X("oled:VCC"))])
wire("imu:GND", "oled:GND", "gnd", [("y", PSG), ("x", X("oled:GND"))])
wire("lcd:VCC", "oled:VCC", "pwr", [("x", X("lcd:VCC") - 10), ("y", PS3), ("x", X("oled:VCC"))])
wire("lcd:GND", "oled:GND", "gnd", [("x", X("lcd:GND") - 40), ("y", PSG), ("x", X("oled:GND"))])
wire("lcd:VCC", "esp:3V3", "pwr", [("x", X("lcd:VCC") - 10), ("y", PS3), ("x", XR),
                                   ("y", TOP - 8), ("x", ex("3V3"))])
wire("lcd:GND", "esp:GND.2", "gnd", [("x", X("lcd:GND") - 40), ("y", PSG), ("x", XRG),
                                     ("y", BOT + 9), ("x", ex("GND.2"))])

# ================================================================== labels and legend
def group_title(pid, x, y, s):
    label(pid, x, y, s, size=18, color="#0f172a")


xs = [p.bbox() for p in parts.values() if p.type != "wokwi-text"]
TOP_Y = min(b[1] for b in xs)
group_title("t_power", led_pwr.bbox()[0] - 10, LV - 60, "ALIMENTARE ȘI MOTOARE")
group_title("t_manual", enc.bbox()[0] - 10, enc.bbox()[1] - 40, "REGLAJ MANUAL")
group_title("t_panel", buz.bbox()[0], GND_LANE + 16, "INTERFAȚĂ OPERATOR")
group_title("t_sens", lim_az.bbox()[0], imu.bbox()[3] + 30, "SENZORI")
group_title("t_disp", oled.bbox()[0], oled.bbox()[3] + 30, "AFIȘAJE (I2C)")
label("t_az", mot_az.bbox()[0] + 40, mot_az.bbox()[1] - 20, "Axa AZIMUT", 13, "#9a3412")
label("t_el", mot_el.bbox()[0] + 40, mot_el.bbox()[1] - 20, "Axa ELEVAȚIE", 13, "#075985")
label("t_lims", lim_az.bbox()[0] - 6, lim_az.bbox()[3] + 4, "LIM AZ", 11)
label("t_lime", lim_el.bbox()[0] - 6, lim_el.bbox()[3] + 4, "LIM EL", 11)
label("t_relay", relay.bbox()[0], relay.bbox()[1] - 22, "releu: taie VMOT la E-STOP", 11)
leg_x = lcd.bbox()[0]
leg_y = lcd.bbox()[3] + 30
label("t_leg", leg_x, leg_y, "Culori fire", 14, "#0f172a")
for i, (k, (col, text)) in enumerate(COLORS.items()):
    label(f"leg_{k}", leg_x + (i % 2) * 190, leg_y + 22 + (i // 2) * 18, "■ " + text, 12, col)

out = {
    "version": 1,
    "author": "POLARIS SAT-1",
    "editor": "wokwi",
    "parts": [p.to_json() for p in parts.values()],
    "connections": wires,
    "dependencies": {},
}

if __name__ == "__main__":
    dest = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "firmware" / "diagram.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"{dest}: {len(parts)} parts, {len(wires)} wires")
