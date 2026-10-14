# sgp4_vallado

Official SGP4 propagator by David Vallado, revision 2020-07-13
(`SGP4.cpp`, `SGP4.h`), taken from the source distribution of
python-sgp4 2.27 (`extension/`), MIT license (`LICENSE-python-sgp4.txt`).
Vallado's code is distributed freely with the paper
"Revisiting Spacetrack Report #3" (AIAA 2006-6753).

Changes, nothing else touched:
- `twoline2rv()` and `#include <iostream>` are inside `#ifdef SGP4_WITH_TWOLINE2RV`
  (the function is interactive, uses scanf/printf). The firmware parses
  TLEs itself in `pc_orbit.cpp`, with the same columns and unit conversion.
- `library.json` compiles this file with `-w` (third-party code, kept as is).

Verification: `firmware/test_native` runs the official SGP4-VER.TLE cases;
all 659 reference points match `tcppver.out` within 0.12 mm.
