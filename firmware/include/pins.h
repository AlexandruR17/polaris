// POLARIS SAT-1 pin map (ESP32 DevKitC V4). Same table in README.md.
#pragma once

// Azimuth axis, A4988 #1
constexpr int PIN_AZ_STEP = 26;
constexpr int PIN_AZ_DIR = 25;
constexpr int PIN_AZ_EN = 27;  // active low
// Elevation axis, A4988 #2
constexpr int PIN_EL_STEP = 33;
constexpr int PIN_EL_DIR = 32;
constexpr int PIN_EL_EN = 14;  // active low
// MS1/MS2/MS3 of both drivers are tied to 3V3: 1/16 microstepping

// I2C bus: MPU6050 (0x68), SSD1306 (0x3C), LCD 2004 PCF8574 (0x27)
constexpr int PIN_SDA = 21;
constexpr int PIN_SCL = 22;

// Limit switches, NC to GND: LOW = ok, HIGH = triggered or broken wire
constexpr int PIN_LIM_AZ = 39;  // input only (VN), driven by the switch
constexpr int PIN_LIM_EL = 19;

// Operator interface
constexpr int PIN_ENC_CLK = 34;  // input only, KY-040 has pull-ups
constexpr int PIN_ENC_DT = 35;   // input only
constexpr int PIN_ENC_SW = 5;
constexpr int PIN_POT = 36;      // VP, ADC1
constexpr int PIN_BTN_MODE = 4;
constexpr int PIN_BTN_HOME = 16;
constexpr int PIN_BTN_STOW = 17;
constexpr int PIN_ESTOP = 13;    // pressed = LOW

// Outputs
constexpr int PIN_RELAY = 23;    // HIGH = motor power on
constexpr int PIN_BUZZER = 18;
constexpr int PIN_LED_GREEN = 2;
constexpr int PIN_LED_YELLOW = 15;
constexpr int PIN_LED_RED = 12;
