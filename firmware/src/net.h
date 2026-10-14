// WiFi, NTP and TLE download from CelesTrak.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace net {

bool connectWifi(uint32_t timeoutMs);
// true when the clock was set by NTP, otherwise the build time is used
bool syncTime(uint32_t timeoutMs);
double nowUnix();

struct Tle {
  char name[25];
  char l1[72];
  char l2[72];
};

// GET https://celestrak.org/NORAD/elements/gp.php?CATNR=<id>&FORMAT=TLE
bool downloadTle(long catnr, Tle& out, uint32_t timeoutMs);

}  // namespace net
