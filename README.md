# POLARIS SAT-1

**English** · [Română](README.ro.md)

**Vehicle-mounted satellite tracking antenna with tilt compensation.**
Project for the Advanced Mechatronic Systems course (Sisteme Mecatronice Avansate).

![Wokwi circuit](docs/img/wokwi_diagram.png)

![POLARIS Ground Station during an ISS pass](docs/img/dashboard_track.png)

Contents:

1. [What it is](#1-what-it-is)
2. [Architecture and repository layout](#2-architecture-and-repository-layout)
3. [Pin table](#3-pin-table)
4. [Wokwi demo, step by step](#4-wokwi-demo-step-by-step)
5. [Wokwi → dashboard link](#5-wokwi--dashboard-link)
6. [Simulation without Wokwi](#6-simulation-without-wokwi)
7. [The math](#7-the-math)
8. [Verification and results](#8-verification-and-results)
9. [Physical build](#9-physical-build)
10. [Simulation limits and how to solve them on real hardware](#10-simulation-limits-and-how-to-solve-them-on-real-hardware)

The user interface (LCD, OLED, dashboard) is in Romanian, as required by the course. Where this
README quotes an on-screen text, the English meaning is given next to it.

---

## 1. What it is

POLARIS SAT-1 is a two-axis (azimuth and elevation) antenna pedestal driven by two stepper
motors. It sits on a vehicle and keeps the antenna pointed at a real satellite:

- it gets the exact time over the internet (NTP);
- it downloads the orbital elements (TLE) from CelesTrak;
- it uses the SGP4 model to compute where the satellite is, as seen from Politehnica University
  of Bucharest (44.4386° N, 26.0494° E, 80 m);
- it measures how much the vehicle is tilted (MPU6050 accelerometer);
- it corrects the motor commands so the antenna stays on the satellite even when the vehicle is
  on a slope or rocking.

Predefined satellites: **ISS (25544)**, **NOAA 19 (33591)**, **NOAA 18 (28654)** and a
geostationary satellite, **Es'hail 2 / QO-100 (43700)**, used by radio amateurs in Europe. Any
other NORAD number can be requested with the `SAT:<id>` command.

**The name.** Polaris is the North Star, the fixed point navigators steered by for centuries.
The antenna does the same thing the other way round: it stays locked on a target while its own
base moves. SAT-1 means the first prototype of the satellite tracking system.

**Real-world equivalents.**

- SATCOM-on-the-move (COTM) antennas on military and emergency vehicles, for example the Ku/Ka
  terminals from Cobham, Gilat or Hughes.
- Stabilized maritime VSAT antennas (Intellian, KVH), which compensate the ship's roll and pitch.
- Mobile ground stations for weather satellites (NOAA APT, Meteor LRPT) used in the field.
- Amateur radio rotators such as the Yaesu G-5500 and SPID, driven by Gpredict or SatPC32. These
  are fixed, with no compensation.

POLARIS reproduces the same loop at lab scale: orbit prediction, coordinate transformation into
the vehicle frame, motion planning and safety.

## 2. Architecture and repository layout

```
           WiFi (Wokwi-GUEST)                       serial JSON 115200
  NTP ──────────┐   CelesTrak TLE                  ┌───────────────────────────────┐
                ▼        ▼                         │  POLARIS Ground Station (web) │
        ┌──────────────────────────┐   telemetry   │  3D globe, sky plot, 3D       │
        │ ESP32 DevKit             │ ─────────────►│  vehicle, charts, pass table, │
        │  core 0: control 50 Hz   │   events      │  log, skyfield cross-check,   │
        │    SGP4 10 Hz, states,   │ ◄──────────── │  results in SQLite            │
        │    compensation, safety  │   commands    └───────────────────────────────┘
        │  core 0: network (TLE)   │
        │  core 1: motor steps     │──► 2× A4988 ──► 2× NEMA 17 + 5:1 gearbox
        └──────────────────────────┘
          ▲ MPU6050  ▲ limit switches  ▲ buttons, encoder, pot.  ▼ OLED, LCD, LEDs, buzzer
```

The key idea: **all the logic (orbit, geometry, tracking, states, protocol) lives in a C++
library with no Arduino dependency**, `firmware/lib/polaris_core`. It compiles for the ESP32 and
also natively on a PC, for tests. An identical Python copy (`ground_station/polaris_gs/sim`) runs
inside the dashboard when Wokwi is not available. A test compares the two implementations step
by step.

```
polaris/
├── firmware/                      PlatformIO, ESP32
│   ├── platformio.ini             envs: esp32dev_sim, esp32dev_hw, esp32dev_qemu
│   ├── wokwi.toml, diagram.json   Wokwi simulation (RFC2217 port 4000)
│   ├── include/pins.h             pin map
│   ├── src/main.cpp               FreeRTOS tasks, motors (AccelStepper), IMU
│   ├── src/hmi.cpp                LCD, OLED, buttons, encoder, buzzer, LEDs
│   ├── src/net.cpp                WiFi, NTP, TLE download (HTTPS)
│   ├── lib/polaris_core/          portable logic: pc_orbit, pc_geometry, pc_tracking,
│   │                              pc_filter, pc_protocol, pc_controller, pc_config
│   ├── lib/sgp4_vallado/          SGP4 Vallado 2020 (reference implementation)
│   └── test_native/               g++ test of the logic, state machine scenarios
├── ground_station/                web dashboard (Python server + page) + Python copy of the firmware
│   ├── polaris_gs/core/           geometry, orbit, tracking, protocol, fallback TLEs
│   ├── polaris_gs/sim/            controller.py (firmware copy), runner.py
│   ├── polaris_gs/server.py       aiohttp web server, WebSocket to the page
│   ├── polaris_gs/hub.py          link, telemetry history, SQLite, skyfield, vehicle stream
│   ├── polaris_gs/web/            the page: globe, sky plot, 3D vehicle, charts (three.js, uPlot)
│   └── tests/                     pytest (89 tests)
├── tools/
│   ├── wokwi/                     generate, check and render diagram.json; wokwi.com bundle
│   ├── experiments.py             the experiments in section 8
│   ├── screenshots.py             dashboard screenshots (headless Chromium)
│   ├── qemu_smoke.py              runs the real ESP32 binary in QEMU
│   └── schematic.py               electrical schematic for the physical build
└── docs/
    ├── img/                       screenshots
    ├── results/                   tables, CSV, plots, SQLite
    └── hardware/                  schematic (svg, png), bill of materials
```

**States** (every change sends a `MODE` event on the serial port):

| State | What it does |
|---|---|
| BOOT | WiFi, NTP, TLE, splash screen with the version |
| HOMING | both axes seek their limit switch, then set their origin; over 45 s → FAULT |
| IDLE | holds position, motors enabled |
| WAIT_AOS | has computed the next pass and waits at the rise azimuth (or in STOW) |
| ACQUIRE | slews to the satellite; switches to TRACK when the error drops below 1° |
| TRACK | follows the satellite while its elevation is above 5° |
| STOW | parking position (azimuth 0°, elevation 90°) |
| MANUAL | the encoder moves the selected axis, the potentiometer sets the speed |
| DEMO | jumps ahead in time to the next good pass and runs it at x10, x30 or x60 |
| ESTOP | motors off; leaving it requires releasing the button and confirming (HOME or `ACK`) |
| FAULT | limit switch hit outside homing, or homing timed out; leaving it requires confirmation |

**Serial protocol** (115200 baud, one JSON line per message):

```
telemetry, 10 Hz:
{"t_utc":"2026-10-15T03:44:48.7Z","sat":25544,"sat_az":217.90,"sat_el":5.31,"range_km":1838.0,
 "cmd_az":217.90,"cmd_el":5.31,"ant_az":217.94,"ant_el":5.27,"roll":0.00,"pitch":0.00,"yaw":90.00,
 "err_deg":0.059,"mode":"TRACK","next_aos":"...","next_los":"...","max_el":42.9,"warp":30,
 "comp":1,"kh":0,"src":"NET","tle_age":60.0,"tle_fb":1,"axis":"AZ"}
events:
{"ev":"BOOT"} {"ev":"MODE","from":..,"to":..} {"ev":"HOME_OK"} {"ev":"PASS",..} {"ev":"AOS",..}
{"ev":"LOS","max_err":..,"rms_err":..,"n":..,"comp":..,"warp":..} {"ev":"KEYHOLE"} {"ev":"RATE_LIMIT"}
{"ev":"WRAP"} {"ev":"ESTOP"} {"ev":"FAULT","reason":..} {"ev":"ACK"} {"ev":"CMD"} {"ev":"ERR"} {"ev":"INFO"}
commands (plain text, one line):
SAT:25544   MODE:AUTO|MANUAL|DEMO|IDLE|STOW   WARP:10|30|60   VEH:roll,pitch,yaw   VEH:OFF
JOG:AZ,5.0   HOME   STOW   ACK   COMP:0|1
```

## 3. Pin table

| Function | GPIO | Part | Notes |
|---|---|---|---|
| AZ DIR | 32 | A4988 #1 DIR | |
| AZ STEP | 33 | A4988 #1 STEP | |
| AZ ENABLE | 25 | A4988 #1 ENABLE | active LOW |
| EL DIR | 26 | A4988 #2 DIR | |
| EL STEP | 27 | A4988 #2 STEP | |
| EL ENABLE | 14 | A4988 #2 ENABLE | active LOW |
| MS1, MS2, MS3 | 3V3 | both drivers | 1/16 microstepping, fixed by wiring |
| E-STOP | 12 | E-STOP button | INPUT_PULLUP, pressed = LOW, edge interrupt |
| Relay | 13 | relay module (VMOT) | HIGH = motor power on |
| Potentiometer | 36 (VP) | potentiometer | ADC1, MANUAL speed |
| Encoder CLK | 39 (VN) | KY-040 CLK | input only |
| Encoder DT | 34 | KY-040 DT | input only |
| Encoder SW | 35 | KY-040 SW | input only, external 10 kΩ pull-up |
| I2C SDA | 23 | MPU6050, OLED, LCD | |
| I2C SCL | 22 | MPU6050, OLED, LCD | |
| AZ limit | 21 | NC limit switch to GND | internal pull-up, HIGH = hit or broken wire |
| EL limit | 19 | NC limit switch to GND | same |
| MODE button | 18 | button | AUTO → MANUAL → DEMO → AUTO |
| HOME button | 5 | button | homing; in ESTOP/FAULT it confirms |
| STOW button | 17 | button | parking |
| Green LED | 16 | LED + 220 Ω | TRACK (steady), ACQUIRE (blinking) |
| Yellow LED | 4 | LED + 220 Ω | waiting (steady), HOMING (blinking) |
| Red LED | 2 | LED + 220 Ω | ESTOP (steady), FAULT (blinking) |
| Buzzer | 15 | buzzer | AOS, LOS, alarms |

I2C addresses: MPU6050 0x68, SSD1306 OLED 0x3C, PCF8574 LCD 0x27.

**Mechanics and resolution.** 200 steps/rev motor × 1/16 microstepping × 5:1 gearbox =
**16000 microsteps per antenna revolution**, i.e. **0.0225° per microstep**. A 70 cm Yagi has a
30-40° beam, and a 1 m L-band dish about 13°. The resolution is therefore a few hundred times
finer than needed; the gearbox is chosen mainly for torque.

**Wire colors in Wokwi** (the same legend is drawn on the diagram, in Romanian):

| Color | Meaning |
|---|---|
| red | 3V3 logic supply |
| dark red | motor supply, through the relay |
| black | ground (GND) |
| orange | STEP / DIR / ENABLE |
| purple | motor coils |
| magenta | E-STOP and relay |
| teal | encoder and potentiometer |
| blue | I2C bus |
| green | limit switches |
| yellow | buttons, LEDs, buzzer |

## 4. Wokwi demo, step by step

### Option A: Wokwi for VS Code (recommended, connects to the dashboard)

1. Install VS Code, the **PlatformIO IDE** extension and the **Wokwi Simulator** extension.
   Activate the free Wokwi license: F1 → "Wokwi: Request a New License".
2. Open the `firmware/` folder in VS Code.
3. Build the simulation variant:
   ```
   pio run -e esp32dev_sim
   ```
   This produces `.pio/build/esp32dev_sim/firmware.factory.bin`, which `wokwi.toml` points to.
4. F1 → **"Wokwi: Start Simulator"**. The circuit opens and the simulation starts.

### Option A, everything from VS Code with the project tasks

Open the whole `polaris` folder in VS Code (`code C:\polaris`). `.vscode/tasks.json` has ready
tasks (Terminal → Run Task…); VS Code also recommends the two extensions it needs.

1. Once: **Run Task → "POLARIS: instalare dashboard"** (Python environment for the web page).
2. Once: F1 → **"Wokwi: Select Config File"** → `firmware/wokwi.toml`.
3. Every time: **Ctrl+Shift+B** ("POLARIS: firmware + dashboard (Wokwi)"): builds the
   firmware, then starts the web page on http://localhost:8080, which waits for Wokwi.
4. F1 → **"Wokwi: Start Simulator"**. The page connects by itself within 2 seconds.

Other tasks: "POLARIS: dashboard (simulare internă)" (the page without Wokwi) and
"POLARIS: compilare firmware (Wokwi)".

### Option B: in the browser, on wokwi.com

1. Generate a flat folder with all the sources:
   ```
   python tools/wokwi/make_web_bundle.py
   ```
   The result is in `build/wokwi_web/`: `sketch.ino`, the `.cpp/.h` files, `diagram.json` and
   `libraries.txt`.
2. On wokwi.com create a new "ESP32" project. Replace `diagram.json`, upload the other files
   (file menu → "Upload file(s)") and press Start.
3. Note: wokwi.com builds into a 1.25 MB partition and the firmware uses 92.4% of it (checked
   with the same build locally). It has no serial port to the dashboard; use option A for that.

### What to try and what you see

Keyboard shortcuts work after clicking on the circuit area.

| Action | What you see |
|---|---|
| Start the simulation | OLED: splash screen "POLARIS", "fw 1.0.0". LCD: "POLARIS SAT-1", "firmware 1.0.0", then the WiFi, NTP, TLE steps on the last line. Serial: `{"ev":"BOOT",...}` and `INFO` messages. |
| Wait 5-10 s | HOMING: the yellow LED blinks, both motors turn toward the end of travel. In the simulation build the limit is considered reached after a known number of steps. Then `HOME_OK`. |
| After homing | WAIT_AOS: the LCD shows the satellite (ISS), the next AOS, the max elevation and the countdown ("AȘTEPTARE" = waiting). The antenna goes to the rise azimuth. Yellow LED steady. |
| **MODE** button (key `m`) twice | AUTO → MANUAL → DEMO. In DEMO the system jumps to the next good ISS pass (max elevation ≥ 20°) and runs it 30 times faster. |
| In DEMO, at AOS | Short beep, ACQUIRE (green blinks), then TRACK (green steady). The motors follow the satellite; the OLED draws the track on a polar sky plot. |
| Move the **MPU6050** sliders (accel X/Y) | Roll and pitch change on the OLED and the motor commands change so the antenna stays on the satellite (compensation). |
| At LOS | Double beep, a `LOS` event with the max and RMS error, then the next pass is computed. |
| **MODE** once more | AUTO: real-time tracking of real passes. |
| **MODE** until MANUAL | The encoder moves the azimuth 0.5° per click; pressing the encoder switches to elevation. The potentiometer sets the speed (1-20°/s). |
| **STOW** button (key `s`) | The antenna goes to azimuth 0°, elevation 90°. |
| **E-STOP** button (key `e`) | Immediately: the relay drops (the blue "MOTOARE" = motors LED goes off), ENABLE is released, red LED steady, buzzer, `{"ev":"ESTOP"}`. |
| **HOME** (key `h`) after E-STOP | Confirmation (`ACK`), then homing again. If E-STOP is still pressed you get `ERR ESTOP_ACTIVE`. |
| Move a **limit switch** slider outside homing | Simulates a broken wire or over-travel: FAULT `LIMIT_AZ` or `LIMIT_EL`, red LED blinks. Move the slider back, then HOME. |
| Type `SAT:33591` in the serial monitor | Switches to NOAA 19, downloads its TLE and computes the pass. |
| `WARP:60`, `MODE:DEMO` | DEMO 60 times faster. |
| `VEH:5,-3,120` | Sends the vehicle attitude by hand (roll 5°, pitch −3°, yaw 120°). `VEH:OFF` goes back to the MPU6050. |
| `SAT:43700` | The geostationary satellite: a fixed point in the sky, no AOS/LOS. The antenna holds still (with compensation). |

## 5. Wokwi → dashboard link

The dashboard ("POLARIS Ground Station") is a **web page**. A small Python server
(`python -m polaris_gs`) talks to the controller and serves the page on
**http://localhost:8080**; the browser opens by itself. The server is needed because a browser
cannot open the Wokwi RFC2217 port or a COM port on its own; it also keeps the SQLite results and
runs the skyfield cross-check.

`wokwi.toml` contains `rfc2217ServerPort = 4000`. While the simulation runs in VS Code, the
ESP32 serial port is available on `localhost:4000`:

```
cd ground_station
pip install -e .
python -m polaris_gs --link rfc2217://localhost:4000
```

For a real ESP32 board: `python -m polaris_gs --link COM3` (Windows) or
`--link /dev/ttyUSB0` (Linux). The link can also be changed from the page ("Legătură" panel).
Other options: `--port 8080` (web port), `--host 0.0.0.0` (open the page from a phone on the same
network), `--no-browser`, `--db <file.sqlite>`.

```
 Wokwi / ESP32 ──serial JSON──► polaris_gs server (Python) ──WebSocket──► browser page
                ◄──commands───  link, SQLite, skyfield      ◄──buttons───  three.js, uPlot
```

On the first visit the page plays a short intro (title, what the system does, a GO / NO-GO poll built
from live data, then the globe flies in). It runs once per browser; the INTRO button or `?intro=1`
replays it, Esc skips it.

The page uses a mission control layout: the globe fills the screen, a T−/T+ clock counts down to
AOS, a timeline shows AOS, maximum elevation and LOS, and ring gauges show the antenna and vehicle.

What the page shows:

- **3D globe** (three.js): the Earth, the orbit, the ground track, the visibility cone and the
  satellite. Drag to rotate, scroll to zoom.
- **Sky plot**: the pass track, the satellite position (blue) and where the antenna really points
  (orange cross).
- **3D vehicle** (three.js): the vehicle tilted by roll, pitch and yaw, with the antenna turned
  exactly like the motors. The orange line is the antenna axis and the blue line the true
  direction to the satellite; when they overlap, tracking is good.
- **Charts** (uPlot), last 2 minutes: pointing error, axis speeds, vehicle tilt.
- **Upcoming passes**, with the rise time cross-checked against skyfield (Δ sky), and a
  **"Rezultate SQLite"** tab with the saved passes.
- **Controls**: link, satellite, mode, warp, HOME, STOW, ACK, vehicle profile, compensation
  on/off, JOG, a free serial command field, and (simulation only) E-STOP and limit switch fault.
- **Event log**.
- **skyfield cross-check** in the header: the server independently recomputes the satellite
  position with skyfield and shows the difference to the firmware (≈ 0.05°, limited by telemetry
  rounding).
- At every LOS the pass result is saved to **SQLite** (`~/.polaris/polaris.sqlite`), with or
  without compensation, so they can be compared.

The page also works on a phone or tablet: the panels stack in one column.

The vehicle profile ("Staționar" = stationary, "Drum denivelat" = bumpy road, "Viraj" = turn,
"Pantă" = slope) sends `VEH` commands 20 times per second, as if the vehicle were moving. This
tests the compensation without moving the MPU6050 sliders by hand.

## 6. Simulation without Wokwi

```
cd ground_station
pip install -e ".[dev]"
python -m polaris_gs                 # internal simulation, opens http://localhost:8080
python -m polaris_gs --online-tle    # internal simulation, TLE downloaded from CelesTrak
```

The `sim` link runs the **Python copy of the firmware** in the server
(`polaris_gs/sim/controller.py`): same states, same constants, same SGP4, same JSON messages.
The motors are modeled with the AccelStepper acceleration profile. The whole page works the same
way. In `sim` mode the "E-STOP (simulare)" and "Injectează limitator AZ" (inject AZ limit)
buttons are also enabled.

![Dashboard after a pass, with the saved result](docs/img/dashboard_after_pass.png)

<img src="docs/img/dashboard_phone.png" alt="Dashboard on a phone" width="260">

## 7. The math

### 7.1 SGP4: where the satellite is

The TLE (two 69-character lines) describes the orbit at a given moment (the epoch). SGP4
propagates the orbit to the requested time, accounting for the Earth's shape (J2, J3, J4),
atmospheric drag (the B\* term) and, for high orbits, the Moon and Sun (SDP4). The result is the
position in the **TEME** frame (equatorial, star-fixed).

The transformation chain in `pc_orbit.cpp` / `orbit.py`:

1. **TEME → ECEF**: rotation about Z by the Greenwich sidereal angle GMST (IAU-82).
2. **Station → ECEF**: lat/lon/alt on the WGS84 ellipsoid.
3. **ECEF → ENU** (East, North, Up) at the station:
   `ENU = R(lat, lon) · (r_sat − r_station)`.
4. **Azimuth and elevation**: `az = atan2(E, N)`, `el = asin(U / |ENU|)`.

Next pass: the firmware samples the elevation every 2 s over 24 h, finds the 5° crossings by
bisection and the maximum by golden-section search. This runs once per pass, not every cycle.
For geostationary satellites (mean motion about 1 rev/day) the search is skipped: the satellite
is either always visible or never.

SGP4 is Vallado's reference implementation (2020), the same one python-sgp4 and skyfield are
built on. The Arduino "SGP4" library (Hopperpop), originally requested, was tested against the
official SGP4-VER vectors and deviated by hundreds of meters to kilometers, so it was replaced
(see section 8).

### 7.2 Transformation into the vehicle frame

The vehicle frame is FLU (x forward, y left, z up, the ROS REP-103 convention). Attitude:

```
R = Rz(yaw) · Ry(pitch) · Rx(roll)          (vehicle → ENU world)
v_vehicle = Rᵀ · v_ENU
```

Yaw is measured from East, counter-clockwise, as in ENU: yaw 90° means the vehicle faces North.
In the vehicle frame:

```
az_pedestal = atan2(−y, x)      (from forward, clockwise, like an azimuth)
el_pedestal = asin(z)
```

Without compensation the command would only be `az_pedestal = az − (90° − yaw)`,
`el_pedestal = el`. On an 8° slope this is off by up to 8° (experiment A5).

**Roll and pitch from the accelerometer.** When the vehicle is still, the accelerometer measures
only gravity:

```
roll  = atan2(a_y, a_z)
pitch = atan2(−a_x, √(a_y² + a_z²))
```

The accelerometer is noisy and also picks up vibration, while the gyroscope drifts over time. A
**complementary filter** combines them: `θ = α·(θ + ω·dt) + (1−α)·θ_accel`, with α = 0.98. The
gyroscope dominates in the short term and the accelerometer in the long term.

Yaw cannot be obtained from the accelerometer. By default it is fixed (90°); the dashboard can
send it with `VEH`. On real hardware it would come from a dual-antenna GPS or a magnetometer
(section 10).

### 7.3 Keyhole and cable wrap

An azimuth-elevation pedestal has a **keyhole at the zenith**. When the satellite passes close to
vertical, the azimuth changes by up to 180° in a few seconds. The required rate is about
`ω_az ≈ ω_sat / cos(el)` and goes to infinity as el → 90°. The motor is limited to 40°/s and
120°/s².

Implemented solutions:

1. **Rate limiting with look-ahead.** At the start of the pass the firmware computes the whole
   azimuth profile and runs it through a forward-backward (zero-phase) rate limiter, so the
   antenna starts turning earlier and does not fall behind after the zenith. On the zenith pass
   (89.4°) the maximum error drops from 1.09° to 0.68° in real time (experiments B1/B2).
2. **The `KEYHOLE` event**: once at planning time (`"pred":1`, with the required and available
   rate), then during the pass when the error exceeds 0.5° because of the rate limit at
   elevations above 70°. When the rate saturates for another reason (for example a sudden yaw
   change) the event is called `RATE_LIMIT`. Both report the error.
3. **Cable wrap.** The azimuth has ±270° of travel, not continuous 360°, because the wires run
   through the joint. At the start of the pass the azimuth branch (θ, θ ± 360°) is chosen
   **once**, so that the whole pass stays within ±270° with the smallest initial slew. This way
   the antenna never has to unwind 360° in the middle of a pass. The choice is reported with the
   `WRAP` event.

### 7.4 Compensation on a moving vehicle

The command is recomputed at 50 Hz with the filtered attitude. The math is exact (test: with
compensation, the remaining error is < 10⁻⁶ ° over 300 random attitudes). The practical limit is
**motor acceleration**: on the simulated bumpy road, the 1.5° components at 1.9 Hz on roll and
1.2° at 2.3 Hz on pitch alone need more than 200°/s² (A·ω²), while the motors have 120°/s².
Experiments A2/A3/A6 show exactly this (section 8).

## 8. Verification and results

### What was verified and how

| Check | How | Result |
|---|---|---|
| Firmware SGP4 vs the official SGP4-VER vectors (Vallado) | native g++ test + pytest | 659 points, max deviation 0.12 mm |
| Python copy vs skyfield (az/el) | pytest, all satellites, 24 h | ≤ 0.004° (requirement: < 0.1°) |
| C++ vs Python math (ENU → vehicle, roll/pitch, GMST, wrap, rate limiting) | parity test, 300 random cases | difference < 10⁻⁹ ° |
| C++ vs Python command parser | the same 29 lines, including invalid ones | same responses and errors |
| C++ vs Python state machine | 5 scenarios (demo with tilt, keyhole, safety, homing timeout, manual GEO) | same event sequence and telemetry |
| Unit tests | `pytest` (89 tests, including the web server and WebSocket protocol) | all pass |
| ESP32 firmware | `pio run`, all 3 envs | 0 warnings |
| Real ESP32 binary | Espressif QEMU (`tools/qemu_smoke.py`), commands over UART | BOOT → fallback TLE → HOMING → HOME_OK → MANUAL → JOG → SAT:43700 → AUTO → ACQUIRE → TRACK → VEH → STOW → HOME |
| Wokwi circuit | official `@wokwi/diagram-lint` linter + `check_pins.py` | 0 errors, 0 warnings; 23 pins, all matching `pins.h` |
| Web dashboard | `tools/screenshots.py` drives the page in headless Chromium (boot, DEMO, TRACK, LOS, phone width), fails on any JavaScript error; screenshots checked visually | `docs/img/` |

Commands:

```
cd ground_station && pytest                       # 89 tests
make -C firmware/test_native                      # native g++ test (-Wall -Wextra -Werror)
cd firmware && pio run -e esp32dev_sim            # build for Wokwi
python tools/experiments.py                       # regenerates docs/results
python tools/screenshots.py docs/img              # screenshots (needs: playwright install chromium)
```

**Memory (esp32dev_sim):** RAM 25.5% (83,396 B of 327,680 B), Flash 38.5%
(1,211,503 B of 3,145,728 B, `huge_app` partition).

### Experiments

The error is the true angle between the antenna axis and the direction to the satellite, with the
vehicle tilt applied. It is measured at 50 Hz from AOS to LOS on the Python copy of the firmware.
`tools/experiments.py` regenerates everything (table, CSV, plots, SQLite).

| ID | Scenario | Speed | Max [°] | RMS [°] | P95 [°] |
|---|---|---|---|---|---|
| A1 | stationary | x10 | 0.39 | 0.15 | 0.35 |
| A2 | bumpy road, compensated | x10 | 5.96 | 1.88 | 3.75 |
| A3 | bumpy road, not compensated | x10 | 4.91 | 2.37 | 4.01 |
| A4 | 8° slope, compensated | x10 | 1.16 | 0.16 | 0.39 |
| A5 | 8° slope, not compensated | x10 | 8.31 | 5.57 | 8.22 |
| A6 | bumpy road, compensated, acceleration x3 | x10 | 1.96 | 0.72 | 1.41 |
| B1 | zenith pass, with keyhole planning | x1 | 0.68 | 0.05 | 0.02 |
| B2 | zenith pass, without planning | x1 | 1.09 | 0.06 | 0.02 |
| B3 | zenith pass, with keyhole planning | x10 | 15.92 | 5.01 | 14.51 |
| B4 | zenith pass, without planning | x10 | 24.62 | 4.94 | 13.84 |

Passes used: ISS on 15 Oct 2026 03:44 UTC (max elevation 42.9°) for A and ISS on 17 Aug 2026
03:44 UTC (89.4°) for B, both computed from the stored TLEs so the results are repeatable.

![Error with and without compensation](docs/results/error_compensation.png)

![Keyhole](docs/results/error_keyhole.png)

(Plot labels are in Romanian: "staționar" = stationary, "denivelat" = bumpy, "cu/fără
compensare" = with/without compensation, "cu/fără planificare" = with/without planning.)

**Interpretation.**

- **Slope (A4 vs A5):** compensation cuts the RMS error 35 times (5.57° → 0.16°). Here the math
  does all the work, since the tilt is constant.
- **Bumpy road (A2, A3, A6):** with the baseline motors, compensation only lowers the RMS from
  2.37° to 1.88°, and the peak actually grows. The motors cannot follow 1.9 Hz oscillations at
  120°/s² and lag with a phase that sometimes adds the errors up. With 3x acceleration (A6) the
  RMS drops to 0.72°. Conclusion: on a vehicle the limit is the **actuator**, not the
  computation. This is why real stabilizers use direct-drive motors (section 10).
- **Keyhole (B):** in real time, look-ahead planning lowers the peak from 1.09° to 0.68°. At x10
  any 40°/s pedestal loses the satellite for a few seconds at the zenith, but planning lowers the
  peak from 24.6° to 15.9°. The small P95 values show the error only appears in the few seconds
  around the zenith.

## 9. Physical build

- Schematic: [`docs/hardware/schematic_power.svg`](docs/hardware/schematic_power.svg)
  (power, safety, motors) and
  [`docs/hardware/schematic_logic.svg`](docs/hardware/schematic_logic.svg)
  (ESP32, sensors, operator interface). Generated with `python tools/schematic.py`.
- Bill of materials with indicative Romanian prices: [`docs/hardware/bom.md`](docs/hardware/bom.md)
  (about 650 lei, roughly 130 EUR, without the optional parts). The BOM and the schematic labels
  are in Romanian.

![Power schematic](docs/hardware/schematic_power.png)

![Logic schematic](docs/hardware/schematic_logic.png)

Key points:

- **Power**: 12 V / 5 A → 3 A fuse → switch. From 12 V, an LM2596 buck converter gives 5 V for the
  ESP32 and the LCD. The ESP32 makes 3.3 V internally for the sensors and the A4988 logic.
- **A4988 drivers**: one 100 µF / 35 V capacitor right at VMOT on each. RESET tied to SLEEP.
  MS1-MS3 at 3.3 V (1/16). Set the current through Vref before connecting the motor.
- **The safety chain is hardware**: the E-STOP (latching NC contact) is in series with the relay
  coil. Pressing it cuts the coil, the relay opens VMOT and the motors stop even if the ESP32 has
  hung. A second contact of the button (NO) goes to GPIO12 so the firmware knows what happened,
  releases ENABLE and asks for confirmation.
- **Limit switches are NC to ground**: a broken wire looks like a hit switch, so the system goes
  to a safe state (fail-safe).
- **I2C**: 4.7 kΩ pull-ups to 3.3 V. The LCD module has pull-ups to 5 V; remove them or use a
  level shifter.
- **Optional**: two AS5600 (absolute magnetic encoders on the antenna axes), through a TCA9548A
  multiplexer because they share the same address. They close the position loop (section 10).

Differences between the Wokwi circuit and the physical one (Wokwi doesn't have every part):

| In Wokwi | In the physical build | Reason |
|---|---|---|
| E-STOP = momentary button + relay module driven by GPIO13 | latching NC E-STOP in series with the relay coil | Wokwi has no latching button and no separate coil |
| Limit switches = slide switches | NC micro switches | Wokwi has no mechanical limit switch |
| Motors powered straight from the relay, no 12 V supply | 12 V supply, fuse, LM2596 | Wokwi doesn't simulate power |
| No capacitors on VMOT | 100 µF / 35 V on each driver | same |
| LCD directly on the 3.3 V bus | level shifter or pull-ups removed | Wokwi doesn't simulate voltage levels |

## 10. Simulation limits and how to solve them on real hardware

| Limit in simulation | What it means | Solution on real hardware |
|---|---|---|
| Homing considers the limit reached after a fixed number of steps (`POLARIS_SIMULATION`) | Wokwi has no moving part that presses the switch | The `esp32dev_hw` build waits for the real switch; the 45 s timeout stays |
| The Wokwi motor executes every step | No lost steps, no inertia, no resonance | AS5600 absolute encoders on the axes (already in the schematic) and a position check after homing; correctly set current; measured accelerations |
| The Wokwi MPU6050 gives static values, no noise or vibration | The complementary filter is not tested against real vibration | Elastic IMU mount; offset calibration at startup; Kalman or Madgwick filter |
| Yaw fixed or sent from the dashboard | A real vehicle turns | Dual-antenna GPS (heading), IMU with magnetometer (BNO055), possibly a Z gyro integrated between corrections |
| Fixed station position (Politehnica) | The vehicle moves | GNSS module (NEO-6M): position updated every second in the ENU computation |
| Time comes from NTP (Wokwi-GUEST WiFi) | No network in the field | Time from GNSS (PPS) or a DS3231 RTC |
| TLE downloaded over WiFi | No WiFi in the field; the TLE ages (ISS: about 1-3 km/day) | The firmware shows the TLE age and uses the fallback TLE marked as old ("vechi"); in the field, an LTE modem or an update before leaving |
| Motor speed (40°/s, 120°/s²) limits compensation on a bumpy road | Experiment A2 | Faster motors (closed-loop servos, direct-drive BLDC) or a separately stabilized platform (roll/pitch gimbal) |
| Keyhole at the zenith | Az-el pedestal | A third axis (X-Y or az-el-tilt mount), or the firmware planning, accepting a brief loss |
| Cable limited to ±270° | Wires through the joint | Slip ring: continuous azimuth |
| The Wokwi E-STOP chain goes through software (GPIO13 drives the relay) | Not a category 0 stop | NC E-STOP in series with the relay coil (schematic in section 9) |
| Timing on a real ESP32 (SGP4 at 10 Hz, 50 Hz loop) was checked only in QEMU, not on a board | QEMU has no realistic timing | Measure with `esp_timer_get_time()` on the board; the (unmeasured) estimate is in the hundreds of µs per propagation, far below the 100 ms budget |

---

### Notes on sources

- **Wokwi pins and parts** (`wokwi-a4988`, `wokwi-stepper-motor`, `wokwi-mpu6050`,
  `board-ssd1306`, `wokwi-lcd2004` with `pins: i2c`, `wokwi-ky-040`, `wokwi-relay-module`,
  `wokwi-slide-switch` and the others) were checked against the official `wokwi-docs` and
  `wokwi-boards` (ESP32 DevKit V1), then with the official `@wokwi/diagram-lint` linter.
- **The fallback TLEs** in the firmware come from the Gpredict data files (epochs: ISS and QO-100
  16 Aug 2026, NOAA 18/19 22 Mar 2026). The firmware marks them as old (`tle_fb: 1`, age in days
  on the LCD) until it downloads fresh ones from CelesTrak.
- **Libraries**: AccelStepper, U8g2, LiquidCrystal_I2C, Adafruit MPU6050 (with Adafruit Unified
  Sensor and BusIO) and SGP4 Vallado (bundled in `lib/sgp4_vallado`, license in the same folder).
- Globe coastlines: Natural Earth 1:110m (public domain).
- Web page libraries, copied into `ground_station/polaris_gs/web/vendor` so the page works offline:
  three.js 0.170.0 (MIT), uPlot 1.6.31 (MIT), Barlow and JetBrains Mono fonts (SIL OFL), Material Design Icons via @mdi/js 7.4.47 (Pictogrammers Free License, icons under Apache 2.0).
