"""Ground station console theme: dark, one accent colour, large type for projectors.

Series colours come from the validated dark palette (dataviz skill):
blue #3987e5 is the single UI accent; orange #e0702d is the second series.
Azimuth = orange, elevation = blue (same as the Wokwi diagram arrows).
"""
BG = "#0b1220"          # chart surface and window
PANEL = "#111a2c"
PANEL_2 = "#16223a"
BORDER = "#22314f"
TEXT = "#e6edf7"
TEXT_2 = "#9fb0cc"
MUTED = "#61718f"
ACCENT = "#3987e5"
SECOND = "#e0702d"
GRID = "#1d2a44"
# status (reserved, always with icon + text)
GOOD = "#0ca30c"
WARNING = "#fab219"
CRITICAL = "#d03b3b"

AZ_COLOR = SECOND
EL_COLOR = ACCENT

FONT = "DejaVu Sans"

STATE_RO = {
    "BOOT": "PORNIRE", "HOMING": "CALIBRARE AXE", "IDLE": "REPAUS", "WAIT_AOS": "AȘTEPTARE AOS",
    "ACQUIRE": "CĂUTARE", "TRACK": "URMĂRIRE", "STOW": "PARCAT", "MANUAL": "MANUAL",
    "DEMO": "DEMO", "ESTOP": "OPRIRE DE URGENȚĂ", "FAULT": "DEFECT",
}
STATE_STATUS = {
    "TRACK": GOOD, "ACQUIRE": WARNING, "WAIT_AOS": WARNING, "HOMING": WARNING, "DEMO": WARNING,
    "ESTOP": CRITICAL, "FAULT": CRITICAL,
}

QSS = f"""
* {{ font-family: "{FONT}"; color: {TEXT}; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QFrame#panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; }}
QLabel#panelTitle {{ color: {TEXT_2}; font-size: 13px; font-weight: 600; letter-spacing: 1px; }}
QLabel#bigValue {{ font-size: 21px; font-weight: 700; }}
QLabel#small {{ color: {TEXT_2}; font-size: 12px; }}
QPushButton {{
    background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 7px 10px; font-size: 13px; font-weight: 600; text-align: left;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
QPushButton#danger {{ background: #3a1518; border-color: {CRITICAL}; }}
QComboBox, QLineEdit {{
    background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 8px;
    font-size: 13px;
}}
QComboBox QAbstractItemView {{ background: {PANEL_2}; selection-background-color: {ACCENT}; }}
QCheckBox {{ font-size: 13px; spacing: 8px; }}
QTableWidget {{
    background: {PANEL}; gridline-color: {GRID}; border: none; font-size: 13px;
    alternate-background-color: {PANEL_2};
}}
QHeaderView::section {{
    background: {PANEL_2}; color: {TEXT_2}; border: none; padding: 5px; font-size: 12px;
    font-weight: 600;
}}
QPlainTextEdit {{ background: {PANEL}; border: none; font-family: "DejaVu Sans Mono"; font-size: 12px; }}
QScrollBar:vertical {{ background: {PANEL}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; }}
QSplitter::handle {{ background: {BG}; }}
"""
