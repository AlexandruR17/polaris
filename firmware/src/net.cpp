#include "net.h"

#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>

#include "pc_orbit.h"

namespace net {

bool connectWifi(uint32_t timeoutMs) {
  WiFi.mode(WIFI_STA);
  // Wokwi virtual access point, open, channel 6 (skips the scan)
  WiFi.begin("Wokwi-GUEST", "", 6);
  const uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < timeoutMs) delay(100);
  return WiFi.status() == WL_CONNECTED;
}

// Build time as a last resort clock, so the system still runs offline
static time_t buildTime() {
  static const char* months = "JanFebMarAprMayJunJulAugSepOctNovDec";
  char m[4] = {0};
  int d, y, hh, mm, ss;
  sscanf(__DATE__, "%3s %d %d", m, &d, &y);
  sscanf(__TIME__, "%d:%d:%d", &hh, &mm, &ss);
  struct tm t = {};
  t.tm_year = y - 1900;
  t.tm_mon = (int)((strstr(months, m) - months) / 3);
  t.tm_mday = d;
  t.tm_hour = hh;
  t.tm_min = mm;
  t.tm_sec = ss;
  setenv("TZ", "UTC0", 1);
  tzset();
  return mktime(&t);
}

bool syncTime(uint32_t timeoutMs) {
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  const uint32_t t0 = millis();
  while (millis() - t0 < timeoutMs) {
    if (time(nullptr) > 1700000000) return true;
    delay(200);
  }
  struct timeval tv = {buildTime(), 0};
  settimeofday(&tv, nullptr);
  return false;
}

double nowUnix() {
  struct timeval tv;
  gettimeofday(&tv, nullptr);
  return tv.tv_sec + tv.tv_usec / 1e6;
}

bool downloadTle(long catnr, Tle& out, uint32_t timeoutMs) {
  if (WiFi.status() != WL_CONNECTED) return false;
  WiFiClientSecure client;
  // No certificate pinning: TLEs are public data and every TLE line is
  // checked with its checksum and SGP4 init before use.
  client.setInsecure();
  HTTPClient http;
  char url[96];
  snprintf(url, sizeof(url), "https://celestrak.org/NORAD/elements/gp.php?CATNR=%ld&FORMAT=TLE",
           catnr);
  http.setTimeout(timeoutMs);
  http.setConnectTimeout(timeoutMs);
  if (!http.begin(client, url)) return false;
  const int code = http.GET();
  if (code != 200) {
    http.end();
    return false;
  }
  String body = http.getString();
  http.end();
  // expected: name line, line 1, line 2
  int a = 0;
  char lines[3][80];
  int n = 0;
  while (n < 3 && a < (int)body.length()) {
    int b = body.indexOf('\n', a);
    if (b < 0) b = body.length();
    String ln = body.substring(a, b);
    ln.trim();
    if (ln.length()) {
      strncpy(lines[n], ln.c_str(), sizeof(lines[n]) - 1);
      lines[n][sizeof(lines[n]) - 1] = 0;
      n++;
    }
    a = b + 1;
  }
  if (n < 3 || lines[1][0] != '1' || lines[2][0] != '2') return false;
  if (!orbit::tleChecksumOk(lines[1]) || !orbit::tleChecksumOk(lines[2])) return false;
  if (atol(lines[1] + 2) != catnr) return false;
  strncpy(out.name, lines[0], sizeof(out.name) - 1);
  out.name[sizeof(out.name) - 1] = 0;
  strncpy(out.l1, lines[1], sizeof(out.l1) - 1);
  out.l1[sizeof(out.l1) - 1] = 0;
  strncpy(out.l2, lines[2], sizeof(out.l2) - 1);
  out.l2[sizeof(out.l2) - 1] = 0;
  return true;
}

}  // namespace net
