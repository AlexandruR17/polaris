// Operator interface: OLED, LCD 2004, buttons, encoder, pot, LEDs, buzzer.
#pragma once

#include <stdint.h>

#include "pc_controller.h"

namespace hmi {

void begin();                         // pins, displays, splash screen
void splashStatus(const char* line);  // boot progress on the LCD bottom line
void readInputs(ctl::Inputs& in);     // buttons, encoder, pot, switches
void applyOutputs(const ctl::Outputs& o);
void serviceBuzzer(uint32_t ms);
void drawOled(const ctl::Controller& c);
void drawLcd(const ctl::Controller& c, double tReal);
bool estopPressed();                  // raw level, read from any core

}  // namespace hmi
