# Rezultatele experimentelor

Generat de `tools/experiments.py` (copia Python a firmware-ului, aceleași numere ca ESP32).
Eroarea = unghiul real dintre axa antenei și direcția satelitului, cu înclinarea vehiculului
aplicată, măsurată la 50 Hz de la AOS la LOS (stările ACQUIRE și TRACK). Limite: azimut 40°/s, 120°/s², elevație 30°/s, 120°/s².

| ID | Scenariu | Viteză | Eroare max [°] | RMS [°] | P95 [°] | Eșantioane |
|---|---|---|---|---|---|---|
| A1 | staționar | x10 | 0.39 | 0.15 | 0.35 | 2495 |
| A2 | drum denivelat, cu compensare | x10 | 5.96 | 1.88 | 3.75 | 2490 |
| A3 | drum denivelat, fără compensare | x10 | 4.91 | 2.37 | 4.01 | 2490 |
| A4 | pantă 8°, cu compensare | x10 | 1.16 | 0.16 | 0.39 | 2495 |
| A5 | pantă 8°, fără compensare | x10 | 8.31 | 5.57 | 8.22 | 2495 |
| A6 | drum denivelat, cu compensare, accelerație x3 | x10 | 1.96 | 0.72 | 1.41 | 2490 |
| B1 | zenit x1, cu planificare keyhole | x1 | 0.68 | 0.05 | 0.02 | 25405 |
| B2 | zenit x1, fără planificare | x1 | 1.09 | 0.06 | 0.02 | 25405 |
| B3 | zenit x10, cu planificare keyhole | x10 | 15.92 | 5.01 | 14.51 | 2540 |
| B4 | zenit x10, fără planificare | x10 | 24.62 | 4.94 | 13.84 | 2540 |

![Compensare](error_compensation.png)

![Keyhole](error_keyhole.png)
