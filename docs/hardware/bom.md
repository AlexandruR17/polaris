# Listă de componente (BOM) pentru montajul fizic

Prețurile sunt **estimări orientative** (lei, cu TVA, nivel 2025-2026) pentru magazine românești
de tip Optimus Digital, Sigmanortec, Ardushop sau eMAG. Nu au fost verificate online la data
scrierii (accesul la aceste site-uri a fost blocat în mediul de lucru). Verificați prețul și
stocul înainte de comandă.

| # | Componentă | Cant. | Rol | Preț unitar [lei] | Total [lei] |
|---|---|---|---|---|---|
| 1 | ESP32 DevKitC V4 (ESP32-WROOM-32) | 1 | controler, WiFi | 40 | 40 |
| 2 | Driver A4988 cu radiator | 2 | drivere motoare pas cu pas | 10 | 20 |
| 3 | Motor NEMA 17, 1,5-1,7 A, 200 pași/rot | 2 | azimut, elevație | 60 | 120 |
| 4 | Reductor planetar 5:1 pentru NEMA 17 (sau curea GT2 20T/100T) | 2 | raport 5:1 | 90 | 180 |
| 5 | Sursă 12 V / 5 A | 1 | alimentare motoare | 60 | 60 |
| 6 | Modul coborâtor LM2596 (12 V → 5 V) | 1 | alimentare logică | 8 | 8 |
| 7 | Condensator electrolitic 100 µF / 35 V | 2 | decuplare VMOT lângă fiecare driver | 1 | 2 |
| 8 | Siguranță 3 A cu suport | 1 | protecție | 5 | 5 |
| 9 | Întrerupător basculant 12 V | 1 | pornire | 4 | 4 |
| 10 | Buton E-STOP cu reținere, 1 NC + 1 NO | 1 | oprire de urgență | 30 | 30 |
| 11 | Releu 5 V (sau modul releu) + BC547 + 1N4148 + 1 kΩ | 1 | taie VMOT | 8 | 8 |
| 12 | Limitator mecanic (micro switch cu pârghie), folosit NC | 2 | homing, capăt de cursă | 3 | 6 |
| 13 | Modul MPU6050 (GY-521) | 1 | înclinare vehicul | 15 | 15 |
| 14 | OLED SSD1306 0,96" I2C | 1 | ecran diagnostic | 20 | 20 |
| 15 | LCD 2004 cu modul I2C PCF8574 | 1 | ecran operator | 35 | 35 |
| 16 | Encoder rotativ KY-040 | 1 | jog manual | 6 | 6 |
| 17 | Potențiometru 10 kΩ liniar | 1 | viteză manuală | 3 | 3 |
| 18 | Butoane tactile 12 mm | 3 | MOD, HOME, STOW | 1 | 3 |
| 19 | LED 5 mm verde, galben, roșu + 3 rezistențe 220 Ω | 1 set | stare | 3 | 3 |
| 20 | Buzzer activ 5 V | 1 | alarmă | 3 | 3 |
| 21 | Rezistențe 4,7 kΩ (2) și 10 kΩ (1) | 1 set | pull-up I2C și ENC_SW | 1 | 1 |
| 22 | Translator de nivel I2C BSS138, 4 canale | 1 | LCD la 5 V pe magistrala de 3,3 V | 6 | 6 |
| 23 | Placă de test / PCB prototip, fire Dupont, borne cu șurub | 1 set | cablare | 40 | 40 |
| 24 | Rulment axial 51107 (sau rulment de platan) | 1 | sarcina pe axa de azimut | 25 | 25 |
| 25 | Inel colector (slip ring) 6-12 fire, opțional | 1 | elimină limita de ±270° | 70 | 0 (opțional) |
| | **Total fără opționale** | | | | **≈ 650** |

Opțional, pentru buclă închisă de poziție (secțiunea 10 din README):

| # | Componentă | Cant. | Preț unitar [lei] | Total [lei] |
|---|---|---|---|---|
| O1 | Senzor magnetic AS5600 cu magnet diametral | 2 | 15 | 30 |
| O2 | Multiplexor I2C TCA9548A | 1 | 12 | 12 |
| O3 | Modul GNSS (ex. u-blox NEO-6M) pentru poziție și oră fără rețea | 1 | 50 | 50 |
| O4 | Busolă / IMU cu magnetometru (ex. BNO055) pentru yaw real | 1 | 120 | 120 |

Structura mecanică (platan, furcă, suport antenă) nu este inclusă: depinde de antena aleasă și
poate fi printată 3D (PETG) sau făcută din profil de aluminiu 2020.

## Note de montaj

- Reglați curentul fiecărui A4988 cu potențiometrul de pe placă: `Vref = I_max · 8 · R_sense`.
  Pentru R_sense = 0,1 Ω (cel mai comun la modulele chinezești, de verificat pe placă) și
  1,2 A pe fază, Vref ≈ 0,96 V.
- Condensatorul de 100 µF stă cât mai aproape de pinii VMOT/GND ai driverului.
- Nu conectați și nu deconectați motorul cu driverul alimentat: A4988 se poate distruge.
- Masa (GND) este comună între 12 V, 5 V și ESP32.
- MS1, MS2, MS3 la 3,3 V dau 1/16 micropas: 200 · 16 · 5 = 16000 micropași/rot de antenă,
  adică 0,0225° pe micropas.
