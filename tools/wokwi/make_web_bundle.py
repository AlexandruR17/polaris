"""Flatten the firmware into one folder that can be pasted into wokwi.com.

wokwi.com compiles a sketch folder without subfolders: sketch.ino plus
.cpp/.h files, diagram.json and libraries.txt. This copies src/, include/,
lib/polaris_core and lib/sgp4_vallado side by side.

usage: python tools/wokwi/make_web_bundle.py [out_dir]   (default build/wokwi_web)
"""
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FW = ROOT / "firmware"
LIBRARIES = """# Arduino Library Manager names (wokwi.com)
AccelStepper
U8g2
LiquidCrystal I2C
Adafruit MPU6050
Adafruit Unified Sensor
Adafruit BusIO
"""


def main():
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "wokwi_web"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for d in (FW / "src", FW / "include", FW / "lib" / "polaris_core", FW / "lib" / "sgp4_vallado"):
        for f in sorted(d.iterdir()):
            if f.suffix in (".cpp", ".h"):
                name = "sketch.ino" if f.name == "main.cpp" else f.name
                shutil.copy(f, out / name)
    shutil.copy(FW / "lib" / "sgp4_vallado" / "LICENSE-python-sgp4.txt", out)
    shutil.copy(FW / "diagram.json", out)
    (out / "libraries.txt").write_text(LIBRARIES)
    print(f"{out}: {len(list(out.iterdir()))} files")


if __name__ == "__main__":
    main()
