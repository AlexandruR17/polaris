# POLARIS SAT-1 - plan de lucru

Fiecare etapă se încheie cu verificare prin rulare și cu un commit.

## Etapa 0 - Pregătire
- [x] Verificare unelte (Python, g++, PlatformIO) și acces la rețea
- [x] Verificare componente Wokwi în sursa documentației (wokwi-docs, wokwi-boards)
- [x] TLE-uri reale pentru rezervă (ISS, NOAA 19, NOAA 18, ES'HAIL 2 / QO-100)
- [x] Plan, structură repo, .gitignore

## Etapa 1 - Nucleul matematic Python (referința)
- [x] `polaris_gs/core/geometry.py`: ENU, Rz·Ry·Rx, ENU -> vehicul, az/el piedestal
- [x] `polaris_gs/core/tracking.py`: keyhole, limită de viteză, alegerea sensului (cablu ±270°)
- [x] `polaris_gs/core/orbit.py`: SGP4 (Vallado, WGS72), TEME -> ECEF -> ENU, pasaje AOS/max/LOS
- [x] `polaris_gs/core/protocol.py`: format JSON telemetrie/evenimente, parsare comenzi
- [x] pytest pentru toate de mai sus, inclusiv comparație cu skyfield (< 0,1°)

## Etapa 2 - Firmware ESP32
- [x] `lib/polaris_core`: aceeași matematică și mașina de stări în C++ (fără Arduino.h)
- [x] SGP4: Hopperpop eșuează pe vectorii Vallado -> Vallado 2020 vendorizat, verificat (0,12 mm)
- [x] Test nativ g++ comparat cu referința Python (matematică, parser, 5 scenarii complete)
- [x] `src/`: motoare (AccelStepper, nucleul 1), MPU6050 + filtru complementar,
      OLED (U8g2), LCD 2004 cu diacritice, encoder, butoane, E-STOP + releu, LED-uri, buzzer
- [x] WiFi, NTP, descărcare TLE cu rezervă, protocol serial JSON
- [x] Mod SIMULATION pentru limitatoare
- [x] Compilare PlatformIO fără warning-uri, raport flash/RAM
- [x] Binarul real rulat în QEMU Espressif (tools/qemu_smoke.py)

## Etapa 3 - Circuit Wokwi
- [x] `diagram.json` generat (tools/wokwi/gen_diagram.py), grupat pe funcții, fire colorate, legendă
- [x] `wokwi.toml` (rfc2217ServerPort = 4000), pachet pentru wokwi.com cu `libraries.txt`
- [x] Validare: linterul oficial @wokwi/diagram-lint (0 erori) + check_pins.py (pins.h == diagramă)
- [x] Randare a diagramei cu grafica oficială Wokwi (docs/img/wokwi_diagram.png)

## Etapa 4 - Dashboard „POLARIS Ground Station"
- [x] Legătură rfc2217 / serial / simulare internă (copia firmware-ului)
- [x] Glob 3D, harta cerului, model 3D vehicul, grafice, pasaje, comenzi, jurnal
- [x] Verificare încrucișată skyfield, SQLite
- [x] Capturi verificate vizual

## Etapa 8 - Dashboard web în loc de PySide6
- [x] Server aiohttp + WebSocket, logica stației separată de interfață (hub.py)
- [x] Pagina: glob și vehicul 3D (three.js), cerul polar (canvas), grafice (uPlot), iconițe MDI
- [x] Teste pentru server și protocol, capturi din Chromium headless

## Etapa 5 - Experimente
- [x] Pasaj ISS în DEMO x10: staționar, drum denivelat cu/fără compensare, pantă, accelerație x3
- [x] Keyhole pe pasajul prin zenit (89,4°), cu/fără planificare anticipativă, x1 și x10
- [x] tools/experiments.py generează tabelele (docs/results/experiments.md), CSV, grafice, SQLite

## Etapa 6 - Montaj fizic
- [x] Schemă electrică schemdraw (svg + png)
- [x] Listă de componente cu prețuri orientative

## Etapa 7 - README
- [x] Toate cele 10 secțiuni cerute
