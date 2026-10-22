#include "pc_protocol.h"

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace proto {

static void trimCopy(const char* in, size_t len, char* out, size_t n) {
  size_t a = 0, b = len;
  while (a < b && isspace((unsigned char)in[a])) a++;
  while (b > a && isspace((unsigned char)in[b - 1])) b--;
  size_t k = b - a;
  if (k >= n) k = n - 1;
  memcpy(out, in + a, k);
  out[k] = 0;
}

static void upper(char* s) {
  for (; *s; s++) *s = (char)toupper((unsigned char)*s);
}

static bool parseDouble(const char* s, double& v) {
  char buf[40];
  trimCopy(s, strlen(s), buf, sizeof(buf));
  if (!buf[0]) return false;
  char* end = nullptr;
  v = strtod(buf, &end);
  return end && *end == 0;
}

// Split s on commas into up to maxParts pieces, returns count (or > maxParts)
static int split(char* s, char** parts, int maxParts) {
  int n = 0;
  char* p = s;
  while (true) {
    if (n < maxParts) parts[n] = p;
    n++;
    char* c = strchr(p, ',');
    if (!c) break;
    *c = 0;
    p = c + 1;
  }
  return n;
}

const char* parseCommand(const char* line, Command& out) {
  out = Command();
  char s[96];
  trimCopy(line, strlen(line), s, sizeof(s));
  if (!s[0]) return "empty";
  char name[16];
  char rest[96];
  const char* colon = strchr(s, ':');
  if (colon) {
    trimCopy(s, (size_t)(colon - s), name, sizeof(name));
    trimCopy(colon + 1, strlen(colon + 1), rest, sizeof(rest));
  } else {
    trimCopy(s, strlen(s), name, sizeof(name));
    rest[0] = 0;
  }
  upper(name);

  if (!strcmp(name, "HOME") || !strcmp(name, "STOW") || !strcmp(name, "ACK") || !strcmp(name, "TLE")) {
    if (rest[0]) return "no args";
    if (!strcmp(name, "HOME")) out.cmd = Cmd::HOME;
    else if (!strcmp(name, "STOW")) out.cmd = Cmd::STOW;
    else if (!strcmp(name, "ACK")) out.cmd = Cmd::ACK;
    else out.cmd = Cmd::TLE;
    return nullptr;
  }
  if (!strcmp(name, "SAT")) {
    const size_t len = strlen(rest);
    if (len == 0 || len > 9) return "bad id";
    for (size_t i = 0; i < len; i++)
      if (!isdigit((unsigned char)rest[i])) return "bad id";
    out.cmd = Cmd::SAT;
    out.sat = atol(rest);
    return nullptr;
  }
  if (!strcmp(name, "MODE")) {
    upper(rest);
    static const char* modes[] = {"AUTO", "MANUAL", "DEMO", "IDLE", "STOW"};
    for (const char* m : modes)
      if (!strcmp(rest, m)) {
        out.cmd = Cmd::MODE;
        strncpy(out.mode, m, sizeof(out.mode) - 1);
        return nullptr;
      }
    return "bad mode";
  }
  if (!strcmp(name, "WARP")) {
    char* end = nullptr;
    if (!rest[0]) return "bad warp";
    const long w = strtol(rest, &end, 10);
    if (!end || *end) return "bad warp";
    if (w != 1 && w != 10 && w != 30 && w != 60) return "bad warp";
    out.cmd = Cmd::WARP;
    out.warp = (int)w;
    return nullptr;
  }
  if (!strcmp(name, "COMP")) {
    if (strcmp(rest, "0") != 0 && strcmp(rest, "1") != 0) return "bad comp";
    out.cmd = Cmd::COMP;
    out.comp = rest[0] == '1';
    return nullptr;
  }
  if (!strcmp(name, "VEH")) {
    char up[96];
    strncpy(up, rest, sizeof(up) - 1);
    up[sizeof(up) - 1] = 0;
    upper(up);
    if (!strcmp(up, "OFF")) {
      out.cmd = Cmd::VEH_OFF;
      return nullptr;
    }
    char* parts[3];
    if (split(rest, parts, 3) != 3) return "bad veh";
    double v[3];
    for (int i = 0; i < 3; i++)
      if (!parseDouble(parts[i], v[i])) return "bad veh";
    for (int i = 0; i < 3; i++)
      if (!isfinite(v[i])) return "bad veh";
    if (fabs(v[0]) > MAX_TILT_DEG || fabs(v[1]) > MAX_TILT_DEG) return "tilt range";
    out.cmd = Cmd::VEH;
    out.roll = v[0];
    out.pitch = v[1];
    out.yaw = v[2];
    return nullptr;
  }
  if (!strcmp(name, "JOG")) {
    char* parts[2];
    if (split(rest, parts, 2) != 2) return "bad jog";
    char ax[8];
    trimCopy(parts[0], strlen(parts[0]), ax, sizeof(ax));
    upper(ax);
    if (strcmp(ax, "AZ") != 0 && strcmp(ax, "EL") != 0) return "bad jog";
    double d;
    if (!parseDouble(parts[1], d)) return "bad jog";
    if (!isfinite(d) || fabs(d) > MAX_JOG_DEG) return "jog range";
    out.cmd = Cmd::JOG;
    out.axis[0] = ax[0];
    out.axis[1] = ax[1];
    out.axis[2] = 0;
    out.jogDeg = d;
    return nullptr;
  }
  return "unknown";
}

void isoUtc(double t, char* buf, size_t n) {
  const double fl = floor(t);
  long long secs = (long long)fl;
  const int tenth = (int)((t - fl) * 10.0);
  long long days = secs / 86400;
  long long rem = secs % 86400;
  if (rem < 0) {
    rem += 86400;
    days -= 1;
  }
  // civil_from_days (H. Hinnant)
  const long long z = days + 719468;
  const long long era = (z >= 0 ? z : z - 146096) / 146097;
  const unsigned doe = (unsigned)(z - era * 146097);
  const unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  long long y = (long long)yoe + era * 400;
  const unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const unsigned mp = (5 * doy + 2) / 153;
  const unsigned d = doy - (153 * mp + 2) / 5 + 1;
  const unsigned m = mp < 10 ? mp + 3 : mp - 9;
  if (m <= 2) y++;
  snprintf(buf, n, "%04lld-%02u-%02uT%02d:%02d:%02d.%dZ", y, m, d, (int)(rem / 3600),
           (int)((rem % 3600) / 60), (int)(rem % 60), tenth);
}

void sanitize(const char* in, char* out, size_t n) {
  size_t k = 0;
  for (; *in && k + 1 < n; in++) {
    const char c = *in;
    if (c >= 32 && c < 127 && c != '"' && c != '\\') out[k++] = c;
  }
  out[k] = 0;
}

}  // namespace proto
