"""Check that every GPIO in firmware/include/pins.h is wired in diagram.json
to the part that pins.h says, and that no GPIO is used twice."""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXPECT = {  # pins.h constant -> part:pin in the diagram
    "PIN_AZ_DIR": "drv_az:DIR", "PIN_AZ_STEP": "drv_az:STEP", "PIN_AZ_EN": "drv_az:ENABLE",
    "PIN_EL_DIR": "drv_el:DIR", "PIN_EL_STEP": "drv_el:STEP", "PIN_EL_EN": "drv_el:ENABLE",
    "PIN_ESTOP": "estop:1.r", "PIN_RELAY": "relay:IN", "PIN_POT": "pot:SIG",
    "PIN_ENC_CLK": "enc:CLK", "PIN_ENC_DT": "enc:DT", "PIN_ENC_SW": "enc:SW",
    "PIN_SDA": "imu:SDA", "PIN_SCL": "imu:SCL", "PIN_LIM_AZ": "lim_az:2", "PIN_LIM_EL": "lim_el:2",
    "PIN_BTN_MODE": "btn_mode:1.l", "PIN_BTN_HOME": "btn_home:1.l", "PIN_BTN_STOW": "btn_stow:1.l",
    "PIN_LED_GREEN": "led_g:A", "PIN_LED_YELLOW": "led_y:A", "PIN_LED_RED": "led_r:A",
    "PIN_BUZZER": "buzzer:2",
}
ALIAS = {36: "VP", 39: "VN"}


def main():
    pins = {k: int(v) for k, v in re.findall(r"constexpr int (PIN_\w+) = (\d+);",
                                             (ROOT / "firmware/include/pins.h").read_text())}
    conns = json.loads((ROOT / "firmware/diagram.json").read_text())["connections"]
    edges = {(a, b) for a, b, *_ in conns} | {(b, a) for a, b, *_ in conns}
    errors = []
    if set(pins) != set(EXPECT):
        errors.append(f"constants differ: {set(pins) ^ set(EXPECT)}")
    used = {}
    for name, gpio in pins.items():
        esp = f"esp:{ALIAS.get(gpio, gpio)}"
        if (EXPECT.get(name), esp) not in edges:
            errors.append(f"{name}={gpio}: no wire {EXPECT.get(name)} -> {esp}")
        if gpio in used:
            errors.append(f"GPIO{gpio} used by {used[gpio]} and {name}")
        used[gpio] = name
    for e in errors:
        print("ERROR", e)
    print(f"{len(pins)} pins checked, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
