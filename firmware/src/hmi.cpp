#include "hmi.h"

#include <Arduino.h>
#include "lcd_i2c.h"
#include <U8g2lib.h>
#include <Wire.h>
#include <math.h>
#include <string.h>

#include "pins.h"

#ifndef POLARIS_QEMU
#define POLARIS_QEMU 0
#endif

namespace hmi {

static U8G2_SSD1306_128X64_NONAME_F_HW_I2C oled(U8G2_R0, U8X8_PIN_NONE);
static LiquidCrystal_I2C lcd(0x27, 20, 4);

// ---------------------------------------------------------------- LCD glyphs
// HD44780 has 8 user glyphs: we use them for the Romanian letters.
static uint8_t G_A_BREVE[8] = {0b10001, 0b01110, 0b00000, 0b01110, 0b10001, 0b11111, 0b10001, 0b00000};
static uint8_t G_S_COMMA[8] = {0b01111, 0b10000, 0b01110, 0b00001, 0b11110, 0b00000, 0b00100, 0b01000};
static uint8_t G_T_COMMA[8] = {0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00000, 0b00100, 0b01000};
static uint8_t G_a_breve[8] = {0b10001, 0b01110, 0b00000, 0b01110, 0b00001, 0b01111, 0b10001, 0b01111};
static uint8_t G_s_comma[8] = {0b00000, 0b01111, 0b10000, 0b01110, 0b00001, 0b11110, 0b00100, 0b01000};
static uint8_t G_t_comma[8] = {0b01000, 0b11100, 0b01000, 0b01000, 0b01001, 0b00110, 0b00100, 0b01000};
static uint8_t G_i_circ[8] = {0b00100, 0b01010, 0b00000, 0b01100, 0b00100, 0b00100, 0b01110, 0b00000};
static uint8_t G_a_circ[8] = {0b00100, 0b01010, 0b00000, 0b01110, 0b00001, 0b01111, 0b10001, 0b01111};

// UTF-8 sequence -> LCD code
struct Glyph {
  uint8_t b0, b1, code;
};
static const Glyph GLYPHS[] = {
    {0xC4, 0x82, 0}, {0xC8, 0x98, 1}, {0xC8, 0x9A, 2}, {0xC4, 0x83, 3}, {0xC8, 0x99, 4},
    {0xC8, 0x9B, 5}, {0xC3, 0xAE, 6}, {0xC3, 0xA2, 7}, {0xC2, 0xB0, 0xDF},
    {0xC3, 0x8E, 'I'}, {0xC3, 0x82, 'A'},
};

// Print UTF-8 text on one LCD row, padded to 20 columns
static void lcdRow(int row, const char* s) {
  uint8_t buf[20];
  int n = 0;
  const uint8_t* p = (const uint8_t*)s;
  while (*p && n < 20) {
    if (*p < 0x80) {
      buf[n++] = *p++;
      continue;
    }
    uint8_t code = '?';
    for (const Glyph& g : GLYPHS)
      if (p[0] == g.b0 && p[1] == g.b1) code = g.code;
    buf[n++] = code;
    p += (p[0] & 0xE0) == 0xC0 ? 2 : 3;
  }
  while (n < 20) buf[n++] = ' ';
  static uint8_t shown[4][20];
  static bool valid[4] = {false, false, false, false};
  if (valid[row] && memcmp(shown[row], buf, 20) == 0) return;  // only redraw changes
  memcpy(shown[row], buf, 20);
  valid[row] = true;
  lcd.setCursor(0, row);
  for (int i = 0; i < 20; i++) lcd.write(buf[i]);
}

// ---------------------------------------------------------------- inputs
static volatile int encCount = 0;
static volatile uint32_t encLastUs = 0;
static volatile bool estopEdge = false;

static void IRAM_ATTR onEncoderClk() {
  const uint32_t now = micros();
  if (now - encLastUs < 1500) return;  // contact bounce on real KY-040
  encLastUs = now;
  // CLK falls first when turning clockwise, then DT
  encCount += digitalRead(PIN_ENC_DT) ? 1 : -1;
}

static void IRAM_ATTR onEstop() { estopEdge = true; }

bool estopPressed() {
#if POLARIS_QEMU
  return false;  // QEMU reads every GPIO input as LOW
#else
  return digitalRead(PIN_ESTOP) == LOW || estopEdge;
#endif
}

struct Debounced {
  int pin;
  bool stable;
  bool last;
  uint8_t count;
  // returns true once per press (stable LOW for 2 samples)
  bool pressed() {
    const bool level = digitalRead(pin) == LOW;
    if (level != last) {
      last = level;
      count = 0;
      return false;
    }
    if (count < 2) count++;
    if (count == 2 && level != stable) {
      stable = level;
      return level;
    }
    return false;
  }
};

static Debounced bMode{PIN_BTN_MODE, false, false, 0};
static Debounced bHome{PIN_BTN_HOME, false, false, 0};
static Debounced bStow{PIN_BTN_STOW, false, false, 0};
static Debounced bEnc{PIN_ENC_SW, false, false, 0};

void readInputs(ctl::Inputs& in) {
#if POLARIS_QEMU
  // QEMU reads every GPIO input as LOW: keep the panel idle
  in.btnMode = in.btnHome = in.btnStow = in.encoderPress = false;
  in.encoderDelta = 0;
  in.potFrac = 0.5;
  in.limAz = in.limEl = in.estop = false;
  return;
#endif
  in.btnMode = bMode.pressed();
  in.btnHome = bHome.pressed();
  in.btnStow = bStow.pressed();
  in.encoderPress = bEnc.pressed();
  noInterrupts();
  in.encoderDelta = encCount;
  encCount = 0;
  interrupts();
  in.potFrac = analogRead(PIN_POT) / 4095.0;
  in.limAz = digitalRead(PIN_LIM_AZ) == HIGH;
  in.limEl = digitalRead(PIN_LIM_EL) == HIGH;
  // a short press between two samples is still seen through the edge flag
  in.estop = digitalRead(PIN_ESTOP) == LOW || estopEdge;
  estopEdge = false;
}

// ---------------------------------------------------------------- outputs
struct Tone {
  uint16_t freq, onMs, offMs;
};
static const Tone PAT_AOS[] = {{1500, 80, 60}, {1500, 80, 0}};
static const Tone PAT_LOS[] = {{800, 300, 0}};
static const Tone PAT_ERR[] = {{2500, 60, 60}, {2500, 60, 60}, {2500, 60, 0}};
static const Tone PAT_OK[] = {{2000, 60, 0}};
static const Tone* pat = nullptr;
static int patLen = 0, patIdx = 0;
static uint32_t patNextMs = 0;

static void startPattern(uint8_t beep) {
  switch (beep) {
    case ctl::BEEP_AOS: pat = PAT_AOS; patLen = 2; break;
    case ctl::BEEP_LOS: pat = PAT_LOS; patLen = 1; break;
    case ctl::BEEP_ERROR: pat = PAT_ERR; patLen = 3; break;
    case ctl::BEEP_OK: pat = PAT_OK; patLen = 1; break;
    default: return;
  }
  patIdx = 0;
  patNextMs = 0;
}

void serviceBuzzer(uint32_t ms) {
  if (!pat || ms < patNextMs) return;
  if (patIdx >= patLen) {
    pat = nullptr;
    return;
  }
  tone(PIN_BUZZER, pat[patIdx].freq, pat[patIdx].onMs);  // non-blocking
  patNextMs = ms + pat[patIdx].onMs + pat[patIdx].offMs;
  patIdx++;
}

void applyOutputs(const ctl::Outputs& o) {
  digitalWrite(PIN_LED_GREEN, (o.leds & ctl::LED_GREEN) ? HIGH : LOW);
  digitalWrite(PIN_LED_YELLOW, (o.leds & ctl::LED_YELLOW) ? HIGH : LOW);
  digitalWrite(PIN_LED_RED, (o.leds & ctl::LED_RED) ? HIGH : LOW);
  digitalWrite(PIN_RELAY, o.relayOn ? HIGH : LOW);
  if (o.beep) startPattern(o.beep);
}

// ---------------------------------------------------------------- setup
static void drawStar(int cx, int cy, int r) {
  // four-point star: Polaris
  oled.drawTriangle(cx, cy - r, cx - r / 4, cy, cx + r / 4, cy);
  oled.drawTriangle(cx, cy + r, cx - r / 4, cy, cx + r / 4, cy);
  oled.drawTriangle(cx - r, cy, cx, cy - r / 4, cx, cy + r / 4);
  oled.drawTriangle(cx + r, cy, cx, cy - r / 4, cx, cy + r / 4);
}

void begin() {
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_RELAY, OUTPUT);
  digitalWrite(PIN_RELAY, LOW);  // motor power off until homing
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_BTN_MODE, INPUT_PULLUP);
  pinMode(PIN_BTN_HOME, INPUT_PULLUP);
  pinMode(PIN_BTN_STOW, INPUT_PULLUP);
  pinMode(PIN_ESTOP, INPUT_PULLUP);
  pinMode(PIN_ENC_SW, INPUT_PULLUP);
  pinMode(PIN_ENC_CLK, INPUT);
  pinMode(PIN_ENC_DT, INPUT);
  pinMode(PIN_LIM_AZ, INPUT);
  pinMode(PIN_LIM_EL, INPUT_PULLUP);
#if !POLARIS_QEMU
  analogReadResolution(12);
#endif
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_CLK), onEncoderClk, FALLING);
  attachInterrupt(digitalPinToInterrupt(PIN_ESTOP), onEstop, FALLING);
  digitalWrite(PIN_LED_YELLOW, HIGH);

  oled.begin();
  oled.clearBuffer();
  drawStar(20, 32, 16);
  oled.setFont(u8g2_font_helvB12_tr);
  oled.drawStr(42, 26, "POLARIS");
  oled.setFont(u8g2_font_helvB10_tr);
  oled.drawStr(42, 42, "SAT-1");
  oled.setFont(u8g2_font_5x7_tr);
  oled.drawStr(42, 56, "fw " FW_VERSION);
  oled.sendBuffer();

  lcd.init();
  lcd.backlight();
  lcd.createChar(0, G_A_BREVE);
  lcd.createChar(1, G_S_COMMA);
  lcd.createChar(2, G_T_COMMA);
  lcd.createChar(3, G_a_breve);
  lcd.createChar(4, G_s_comma);
  lcd.createChar(5, G_t_comma);
  lcd.createChar(6, G_i_circ);
  lcd.createChar(7, G_a_circ);
  lcdRow(0, "   POLARIS SAT-1");
  lcdRow(1, "  firmware " FW_VERSION);
  lcdRow(2, "Antenă cu urmărire");
  lcdRow(3, "Pornire...");
}

void splashStatus(const char* line) { lcdRow(3, line); }

// ---------------------------------------------------------------- screens
static const char* stateRo(ctl::State s) {
  switch (s) {
    case ctl::State::BOOT: return "PORNIRE";
    case ctl::State::HOMING: return "CALIBRARE AXE";
    case ctl::State::IDLE: return "REPAUS";
    case ctl::State::WAIT_AOS: return "AȘTEPTARE";
    case ctl::State::ACQUIRE: return "CĂUTARE";
    case ctl::State::TRACK: return "URMĂRIRE";
    case ctl::State::STOW: return "PARCAT";
    case ctl::State::MANUAL: return "MANUAL";
    case ctl::State::DEMO: return "DEMO";
    case ctl::State::ESTOP: return "OPRIRE URGENȚĂ";
    case ctl::State::FAULT: return "DEFECT";
  }
  return "";
}

static const char* shortName(long id) {
  switch (id) {
    case 25544: return "ISS";
    case 33591: return "NOAA 19";
    case 28654: return "NOAA 18";
    case 43700: return "QO-100";
  }
  return "SAT";
}

static void hms(double t, char* out, size_t n) {
  const long s = (long)floor(t);
  const long d = ((s % 86400) + 86400) % 86400;
  snprintf(out, n, "%02ld:%02ld:%02ld", d / 3600, (d % 3600) / 60, d % 60);
}

void drawLcd(const ctl::Controller& c, double tReal) {
  (void)tReal;
  char l[48], t[12], a[12];
  hms(c.tSim(), t, sizeof(t));
  snprintf(l, sizeof(l), "%s UTC %s", t, shortName(c.satId()));
  lcdRow(0, l);
  const orbit::Pass& p = c.pass();
  if (p.valid) {
    hms(p.aos, a, sizeof(a));
    snprintf(l, sizeof(l), "AOS %s az%4.0f°", a, p.aosAz);
    lcdRow(1, l);
    if (p.sets) {
      hms(p.los, a, sizeof(a));
      snprintf(l, sizeof(l), "LOS %s max%3.0f°", a, p.maxEl);
    } else {
      snprintf(l, sizeof(l), "GEO fix  el %4.1f°", p.maxEl);
    }
    lcdRow(2, l);
  } else {
    lcdRow(1, "AOS --:--:--");
    lcdRow(2, "fără pasaj 24 h");
  }
  const ctl::State s = c.state();
  if (s == ctl::State::WAIT_AOS && p.valid) {
    const long dt = (long)(p.aos - c.tSim());
    snprintf(l, sizeof(l), "%s T-%ld:%02ld:%02ld", stateRo(s), dt / 3600, (dt % 3600) / 60,
             dt % 60);
  } else if (s == ctl::State::FAULT) {
    snprintf(l, sizeof(l), "DEFECT %s", c.faultCode());
  } else if (s == ctl::State::MANUAL) {
    snprintf(l, sizeof(l), "MANUAL axa %s", c.manualAxisEl() ? "EL" : "AZ");
  } else if (c.demo()) {
    snprintf(l, sizeof(l), "%s x%d", stateRo(s), c.warp());
  } else {
    snprintf(l, sizeof(l), "%-12s TLE%s", stateRo(s), c.tleFallback() ? " vechi" : " ok");
  }
  lcdRow(3, l);
}

void drawOled(const ctl::Controller& c) {
  char l[24];
  oled.clearBuffer();
  oled.setFont(u8g2_font_5x7_tr);
  static const char* SHORT[] = {"BOOT", "HOME", "IDLE", "WAIT", "ACQ", "TRACK",
                                "STOW", "MAN", "DEMO", "ESTOP", "FAULT"};
  snprintf(l, sizeof(l), "%-7s %s", shortName(c.satId()), SHORT[(int)c.state()]);
  oled.drawStr(0, 7, l);
  snprintf(l, sizeof(l), "T%6.1f%5.1f", c.satAz(), c.satEl());
  oled.drawStr(0, 17, l);
  snprintf(l, sizeof(l), "C%6.1f%5.1f", c.cmdAz(), c.cmdEl());
  oled.drawStr(0, 27, l);
  snprintf(l, sizeof(l), "A%6.1f%5.1f", c.antAz(), c.antEl());
  oled.drawStr(0, 37, l);
  snprintf(l, sizeof(l), "E%6.2f %s", c.errDeg(), c.keyhole() ? "KH" : "");
  oled.drawStr(0, 47, l);
  snprintf(l, sizeof(l), "R%+4.1f P%+4.1f", c.roll(), c.pitch());
  oled.drawStr(0, 57, l);
  snprintf(l, sizeof(l), "%s x%d %s", c.attSource(), c.warp(), c.comp() ? "C" : "-");
  oled.drawStr(0, 64, l);

  // sky plot: centre = zenith, rim = horizon, north up
  const int cx = 96, cy = 32, r = 30;
  oled.drawCircle(cx, cy, r);
  oled.drawCircle(cx, cy, r / 3);
  oled.drawPixel(cx, cy);
  oled.drawStr(cx - 2, 7, "N");
  auto toXY = [&](double az, double el, int& x, int& y) {
    const double rr = r * (90.0 - fmax(0.0, el)) / 90.0;
    x = cx + (int)lround(rr * sin(az * geo::D2R));
    y = cy - (int)lround(rr * cos(az * geo::D2R));
  };
  int x, y;
  if (c.satReady() && c.satEl() > 0) {
    toXY(c.satAz(), c.satEl(), x, y);
    oled.drawDisc(x, y, 2);
  }
  // antenna boresight in the local sky (true pointing, attitude applied)
  const geo::Vec3 b = geo::bodyToEnu(geo::pedestalToBody(c.antAz(), c.antEl()), c.roll(),
                                     c.pitch(), c.yaw());
  const geo::AzEl ae = geo::enuToAzel(b);
  toXY(ae.az, ae.el, x, y);
  oled.drawLine(x - 3, y, x + 3, y);
  oled.drawLine(x, y - 3, x, y + 3);
  oled.sendBuffer();
}

}  // namespace hmi
