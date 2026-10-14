# POLARIS SAT-1 - plan de lucru

Fiecare etapă se încheie cu verificare prin rulare și cu un commit.

## Etapa 0 - Pregătire
- [x] Verificare unelte (Python, g++, PlatformIO) și acces la rețea
- [x] Verificare componente Wokwi în sursa documentației (wokwi-docs, wokwi-boards)
- [x] TLE-uri reale pentru rezervă (ISS, NOAA 19, NOAA 18, ES'HAIL 2 / QO-100)
- [x] Plan, structură repo, .gitignore

## Etapa 1 - Nucleul matematic Python (referința)
- [ ] `polaris/geometry.py`: ENU, Rz·Ry·Rx, ENU -> vehicul, az/el piedestal
- [ ] `polaris/tracking.py`: keyhole, limită de viteză, alegerea sensului (cablu ±270°)
- [ ] `polaris/orbit.py`: SGP4 (Vallado, WGS72), TEME -> ECEF -> ENU, pasaje AOS/max/LOS
- [ ] `polaris/protocol.py`: format JSON telemetrie/evenimente, parsare comenzi
- [ ] pytest pentru toate de mai sus, inclusiv comparație cu skyfield (< 0,1°)

## Etapa 2 - Firmware ESP32
- [ ] `lib/polaris_core`: aceeași matematică în C++ (fără Arduino.h)
- [ ] Test nativ g++ comparat cu referința Python
- [ ] `src/`: mașina de stări, motoare (AccelStepper), MPU6050 + filtru complementar,
      OLED (U8g2), LCD 2004, encoder, butoane, E-STOP + releu, LED-uri, buzzer
- [ ] WiFi, NTP, descărcare TLE cu rezervă, protocol serial JSON
- [ ] Mod SIMULATION pentru limitatoare
- [ ] Compilare PlatformIO fără warning-uri, raport flash/RAM

## Etapa 3 - Circuit Wokwi
- [ ] `diagram.json` complet, grupat pe funcții, fire colorate
- [ ] `wokwi.toml` (rfc2217ServerPort = 4000), `libraries.txt` pentru wokwi.com
- [ ] Validare automată: fiecare pin folosit în firmware există în diagramă
- [ ] Randare a diagramei (imagine) pentru README

## Etapa 4 - Dashboard „POLARIS Ground Station"
- [ ] Legătură rfc2217 / serial / simulare internă (copia firmware-ului)
- [ ] Glob 3D, harta cerului, model 3D vehicul, grafice, pasaje, comenzi, jurnal
- [ ] Verificare încrucișată skyfield, SQLite
- [ ] Capturi offscreen verificate vizual

## Etapa 5 - Experimente
- [ ] Pasaj ISS în DEMO: staționar, drum denivelat cu/fără compensare
- [ ] Script care generează tabelele (Markdown) și graficele

## Etapa 6 - Montaj fizic
- [ ] Schemă electrică schemdraw (svg + png)
- [ ] Listă de componente cu prețuri orientative

## Etapa 7 - README
- [ ] Toate cele 10 secțiuni cerute
