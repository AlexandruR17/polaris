// POLARIS SAT-1 pin map (ESP32 DevKitC V4). Same table in README.md.
// Board left side: motors, safety and the manual control knobs.
// Board right side: sensors (I2C + limit switches) and operator panel.
#pragma once

// Azimuth axis, A4988 #1
constexpr int PIN_AZ_DIR = 32;
constexpr int PIN_AZ_STEP = 33;
constexpr int PIN_AZ_EN = 25;  // active low
// Elevation axis, A4988 #2
constexpr int PIN_EL_DIR = 26;
constexpr int PIN_EL_STEP = 27;
constexpr int PIN_EL_EN = 14;  // active low
// MS1/MS2/MS3 of both drivers are tied to 3V3: 1/16 microstepping

// Safety
constexpr int PIN_ESTOP = 12;  // E-STOP auxiliary contact, pressed = LOW
constexpr int PIN_RELAY = 13;  // HIGH = motor power on

// Manual control (KY-040 + potentiometer)
constexpr int PIN_POT = 36;      // VP, ADC1
constexpr int PIN_ENC_CLK = 39;  // VN, input only, KY-040 has pull-ups
constexpr int PIN_ENC_DT = 34;   // input only
constexpr int PIN_ENC_SW = 35;   // input only, external 10k pull-up

// I2C bus: MPU6050 (0x68), SSD1306 (0x3C), LCD 2004 PCF8574 (0x27)
constexpr int PIN_SDA = 23;
constexpr int PIN_SCL = 22;

// Limit switches, NC contact to GND + internal pull-up:
// LOW = ok, HIGH = triggered or broken wire
constexpr int PIN_LIM_AZ = 21;
constexpr int PIN_LIM_EL = 19;

// Operator panel
constexpr int PIN_BTN_MODE = 18;
constexpr int PIN_BTN_HOME = 5;
constexpr int PIN_BTN_STOW = 17;
constexpr int PIN_LED_GREEN = 16;
constexpr int PIN_LED_YELLOW = 4;
constexpr int PIN_LED_RED = 2;
constexpr int PIN_BUZZER = 15;
