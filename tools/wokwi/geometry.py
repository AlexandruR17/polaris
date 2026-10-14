"""Part geometry for the Wokwi diagram generator and renderer.

Sizes and pin positions in diagram pixels (1 mm = 3.7795 px):
- wokwi-elements parts: measured from @wokwi/elements 1.9.2 in Chromium
  (geom_elements.json, tools/wokwi/measure_elements.py)
- boards: wokwi-boards board.json (mm)
- wokwi-a4988, wokwi-relay-module: SVGs from wokwi-docs (not in wokwi-elements)
Pin names were checked against the part registry of @wokwi/diagram-lint.
"""
import json
import math
import pathlib

MM = 3.7795
HERE = pathlib.Path(__file__).resolve().parent

GEOM = json.loads((HERE / "geom_elements.json").read_text())

# board-esp32-devkit-c-v4, board.json (mm)
_ESP_PINS_MM = {
    "3V3": (1.22, 7.62), "EN": (1.22, 10.16), "VP": (1.22, 12.7), "VN": (1.22, 15.24),
    "34": (1.22, 17.78), "35": (1.22, 20.32), "32": (1.22, 22.86), "33": (1.22, 25.4),
    "25": (1.22, 27.94), "26": (1.22, 30.48), "27": (1.22, 33.02), "14": (1.22, 35.56),
    "12": (1.22, 38.1), "GND.1": (1.22, 40.64), "13": (1.22, 43.18), "D2": (1.22, 45.72),
    "D3": (1.22, 48.26), "CMD": (1.22, 50.8), "5V": (1.22, 53.34),
    "GND.2": (26.66, 7.62), "23": (26.66, 10.16), "22": (26.66, 12.7), "TX": (26.66, 15.24),
    "RX": (26.66, 17.78), "21": (26.66, 20.32), "GND.3": (26.66, 22.86), "19": (26.66, 25.4),
    "18": (26.66, 27.94), "5": (26.66, 30.48), "17": (26.66, 33.02), "16": (26.66, 35.56),
    "4": (26.66, 38.1), "0": (26.66, 40.64), "2": (26.66, 43.18), "15": (26.66, 45.72),
    "D1": (26.66, 48.26), "D0": (26.66, 50.8), "CLK": (26.66, 53.34),
}
GEOM["board-esp32-devkit-c-v4"] = {
    "w": 27.9 * MM, "h": 56.628 * MM,
    "pins": {k: [x * MM, y * MM] for k, (x, y) in _ESP_PINS_MM.items()},
}
GEOM["board-ssd1306"] = {
    "w": 27.7 * MM, "h": 22.6 * MM,
    "pins": {"GND": [10.1 * MM, 1.71 * MM], "VCC": [12.6 * MM, 1.71 * MM],
             "SCL": [15.1 * MM, 1.71 * MM], "SDA": [17.7 * MM, 1.71 * MM]},
}
# wokwi-a4988.svg: 15.2 x 20.3 mm, two columns of 8 pins, 2.54 mm pitch.
# Pololu layout. Logic GND ("GND") is next to VDD, as in the docs pin table.
_A4988_LEFT = ["ENABLE", "MS1", "MS2", "MS3", "RESET", "SLEEP", "STEP", "DIR"]
_A4988_RIGHT = ["VMOT", "GND.1", "2B", "2A", "1A", "1B", "VDD", "GND"]
GEOM["wokwi-a4988"] = {
    "w": 15.2 * MM, "h": 20.3 * MM,
    "pins": {**{n: [1.27 * MM, (1.27 + 2.54 * i) * MM] for i, n in enumerate(_A4988_LEFT)},
             **{n: [13.93 * MM, (1.27 + 2.54 * i) * MM] for i, n in enumerate(_A4988_RIGHT)}},
}
# wokwi-relay-module.svg: 128 x 58.2 px, header on the left, terminals right
GEOM["wokwi-relay-module"] = {
    "w": 128.0, "h": 58.24,
    "pins": {"VCC": [3.8, 19.3], "GND": [3.8, 29.1], "IN": [3.8, 38.6],
             "NC": [113.7, 20.1], "COM": [113.7, 29.7], "NO": [113.7, 39.3]},
}
GEOM["wokwi-buzzer"] = {"w": 64.3, "h": 84.0, "pins": {"1": [27, 84], "2": [37, 84]}}
GEOM["wokwi-text"] = {"w": 0, "h": 0, "pins": {}}


def rotate_point(dx, dy, deg):
    """Clockwise rotation on screen (y down)."""
    a = math.radians(deg)
    c, s = round(math.cos(a), 12), round(math.sin(a), 12)
    return dx * c - dy * s, dx * s + dy * c


class Part:
    def __init__(self, pid, ptype, left, top, rotate=0, attrs=None):
        self.id, self.type = pid, ptype
        self.left, self.top, self.rotate = left, top, rotate
        self.attrs = attrs or {}

    @property
    def g(self):
        return GEOM[self.type]

    @property
    def center(self):
        return self.left + self.g["w"] / 2, self.top + self.g["h"] / 2

    def pin(self, name):
        px, py = self.g["pins"][name]
        cx, cy = self.center
        dx, dy = rotate_point(px - self.g["w"] / 2, py - self.g["h"] / 2, self.rotate)
        return cx + dx, cy + dy

    def bbox(self):
        w, h = self.g["w"], self.g["h"]
        if self.rotate % 180:
            w, h = h, w
        cx, cy = self.center
        return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2

    @staticmethod
    def place_center(pid, ptype, cx, cy, rotate=0, attrs=None):
        g = GEOM[ptype]
        return Part(pid, ptype, cx - g["w"] / 2, cy - g["h"] / 2, rotate, attrs)

    def to_json(self):
        d = {"type": self.type, "id": self.id, "top": round(self.top, 2), "left": round(self.left, 2)}
        if self.rotate:
            d["rotate"] = self.rotate
        d["attrs"] = self.attrs
        return d
