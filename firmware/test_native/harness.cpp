// Native harness: the firmware core (polaris_core) compiled with g++ on the PC.
//   harness math      < queries   math functions, one result per line
//   harness parse     < commands  command parser results
//   harness scenario  < script    full controller run with modelled axes
// The Python tests feed the same input to the Python reference and compare.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <string>
#include <vector>

#include "axis_model.h"
#include "pc_controller.h"
#include "pc_geometry.h"
#include "pc_orbit.h"
#include "pc_protocol.h"
#include "pc_tle_fallback.h"
#include "pc_tracking.h"

static const FallbackTle* findTle(long id) {
  for (int i = 0; i < FALLBACK_TLE_COUNT; i++)
    if (FALLBACK_TLES[i].catnr == id) return &FALLBACK_TLES[i];
  return nullptr;
}

// ------------------------------------------------------------------ math
static int runMath() {
  static char line[16384];
  orbit::Satellite sat;
  long current = 0;
  while (fgets(line, sizeof(line), stdin)) {
    char op[16];
    if (sscanf(line, "%15s", op) != 1) continue;
    if (!strcmp(op, "point")) {
      double az, el, r, p, y;
      int comp;
      sscanf(line + 5, "%lf %lf %lf %lf %lf %d", &az, &el, &r, &p, &y, &comp);
      const geo::AzEl a = geo::pointingCommand(geo::azelToEnu(az, el), r, p, y, comp != 0);
      const double e = geo::pointingError(a.az, a.el, r, p, y, geo::azelToEnu(az, el));
      printf("%.12f %.12f %.12f\n", a.az, a.el, e);
    } else if (!strcmp(op, "err")) {
      double pa, pe, r, p, y, sa, se;
      sscanf(line + 3, "%lf %lf %lf %lf %lf %lf %lf", &pa, &pe, &r, &p, &y, &sa, &se);
      printf("%.12f\n", geo::pointingError(pa, pe, r, p, y, geo::azelToEnu(sa, se)));
    } else if (!strcmp(op, "rp")) {
      double ax, ay, az, r, p;
      sscanf(line + 2, "%lf %lf %lf", &ax, &ay, &az);
      geo::accelToRollPitch(ax, ay, az, r, p);
      printf("%.12f %.12f\n", r, p);
    } else if (!strcmp(op, "look")) {
      long id;
      double t;
      sscanf(line + 4, "%ld %lf", &id, &t);
      if (id != current) {
        const FallbackTle* f = findTle(id);
        sat.init(f->name, f->l1, f->l2);
        current = id;
      }
      orbit::Look l;
      sat.look(t, l);
      printf("%.9f %.9f %.6f\n", l.az, l.el, l.rangeKm);
    } else if (!strcmp(op, "pass")) {
      long id;
      double t;
      sscanf(line + 4, "%ld %lf", &id, &t);
      if (id != current) {
        const FallbackTle* f = findTle(id);
        sat.init(f->name, f->l1, f->l2);
        current = id;
      }
      const orbit::Pass p = sat.nextPass(t, cfg::PASS_SEARCH_H, cfg::MASK_EL_DEG);
      printf("%d %.3f %.3f %d %.3f %.6f %.6f\n", p.valid ? 1 : 0, p.aos, p.los, p.sets ? 1 : 0,
             p.tmax, p.maxEl, p.aosAz);
    } else if (!strcmp(op, "gmst")) {
      double jd;
      sscanf(line + 4, "%lf", &jd);
      printf("%.15f\n", orbit::gmstRad(jd));
    } else if (!strcmp(op, "wrap")) {
      // wrap <current> <n> v1 v2 ...
      double cur;
      int n, off = 0;
      const char* s = line + 4;
      sscanf(s, "%lf %d%n", &cur, &n, &off);
      s += off;
      std::vector<double> v(n);
      for (int i = 0; i < n; i++) {
        sscanf(s, "%lf%n", &v[i], &off);
        s += off;
      }
      trk::unwrapSequence(v.data(), n);
      bool ok;
      const double o = trk::planWrap(v.data(), n, cur, cfg::AZ_MIN_DEG, cfg::AZ_MAX_DEG, ok);
      printf("%.6f %d\n", o, ok ? 1 : 0);
    } else if (!strcmp(op, "ratelim")) {
      // ratelim <dt> <vmax> <n> v1 v2 ...
      double dt, vmax;
      int n, off = 0;
      const char* s = line + 7;
      sscanf(s, "%lf %lf %d%n", &dt, &vmax, &n, &off);
      s += off;
      std::vector<double> v(n), o(n), tmp(n);
      for (int i = 0; i < n; i++) {
        sscanf(s, "%lf%n", &v[i], &off);
        s += off;
      }
      trk::rateLimitFwdBwd(v.data(), o.data(), tmp.data(), n, dt, vmax);
      for (int i = 0; i < n; i++) printf(i ? " %.9f" : "%.9f", o[i]);
      printf("\n");
    } else if (!strcmp(op, "iso")) {
      double t;
      sscanf(line + 3, "%lf", &t);
      char b[40];
      proto::isoUtc(t, b, sizeof(b));
      printf("%s\n", b);
    }
  }
  return 0;
}

// ------------------------------------------------------------------ sgp4ver
// Vallado verification file: line 2 carries start, stop and step (minutes)
static int runSgp4Ver() {
  char a[256], b[256];
  while (fgets(a, sizeof(a), stdin)) {
    if (a[0] != '1') continue;
    if (!fgets(b, sizeof(b), stdin)) break;
    double t0 = 0, t1 = 0, dt = 0;
    sscanf(b + 69, "%lf %lf %lf", &t0, &t1, &dt);
    a[strcspn(a, "\r\n")] = 0;
    b[69] = 0;
    orbit::Satellite s;
    char num[6];
    memcpy(num, a + 2, 5);
    num[5] = 0;
    if (!s.init("VER", a, b, false)) {
      printf("%s INIT_ERR\n", num);
      continue;
    }
    for (double t = t0;; t += dt) {
      if ((dt > 0 && t > t1) || (dt < 0 && t < t1)) t = t1;
      double r[3], v[3];
      if (!s.teme(t, r, v)) {
        printf("%s %.8f ERR\n", num, t);
        break;
      }
      printf("%s %.8f %.8f %.8f %.8f\n", num, t, r[0], r[1], r[2]);
      if (t == t1) break;
    }
  }
  return 0;
}

// ------------------------------------------------------------------ parse
static int runParse() {
  char line[256];
  while (fgets(line, sizeof(line), stdin)) {
    line[strcspn(line, "\n")] = 0;
    proto::Command c;
    const char* err = proto::parseCommand(line, c);
    if (err) {
      printf("ERR %s\n", err);
      continue;
    }
    switch (c.cmd) {
      case proto::Cmd::SAT: printf("SAT %ld\n", c.sat); break;
      case proto::Cmd::MODE: printf("MODE %s\n", c.mode); break;
      case proto::Cmd::WARP: printf("WARP %d\n", c.warp); break;
      case proto::Cmd::VEH: printf("VEH %.6f %.6f %.6f\n", c.roll, c.pitch, c.yaw); break;
      case proto::Cmd::VEH_OFF: printf("VEH OFF\n"); break;
      case proto::Cmd::JOG: printf("JOG %s %.6f\n", c.axis, c.jogDeg); break;
      case proto::Cmd::HOME: printf("HOME\n"); break;
      case proto::Cmd::STOW: printf("STOW\n"); break;
      case proto::Cmd::ACK: printf("ACK\n"); break;
      case proto::Cmd::COMP: printf("COMP %d\n", c.comp ? 1 : 0); break;
      default: printf("NONE\n"); break;
    }
  }
  return 0;
}

// ------------------------------------------------------------------ scenario
static uint32_t gMs = 0;
static void emitLine(void*, const char* line) { printf("%u %s\n", gMs, line); }

struct Step {
  uint32_t ms;
  std::string op, arg;
};

static int runScenario() {
  double t0 = 1792015503.0;
  uint32_t endMs = 60000;
  bool simLimits = true;
  std::vector<Step> steps;
  char line[256];
  while (fgets(line, sizeof(line), stdin)) {
    line[strcspn(line, "\r\n")] = 0;
    if (!line[0] || line[0] == '#') continue;
    if (!strncmp(line, "T0 ", 3)) t0 = atof(line + 3);
    else if (!strncmp(line, "SIMLIMITS ", 10)) simLimits = atoi(line + 10) != 0;
    else if (!strncmp(line, "END ", 4)) endMs = (uint32_t)atol(line + 4);
    else if (line[0] == '@') {
      Step s;
      char op[16] = {0};
      int off = 0;
      unsigned ms = 0;
      sscanf(line + 1, "%u %15s %n", &ms, op, &off);
      s.ms = ms;
      s.op = op;
      s.arg = line + 1 + off;
      steps.push_back(s);
    }
  }

  ctl::Controller c;
  c.begin(simLimits, emitLine, nullptr);
  for (int i = 0; i < FALLBACK_TLE_COUNT; i++)
    c.loadTle(FALLBACK_TLES[i].catnr, FALLBACK_TLES[i].name, FALLBACK_TLES[i].l1,
              FALLBACK_TLES[i].l2, true, t0, false);
  AxisModel az, el;
  az.setPosition(0);
  el.setPosition(0);
  ctl::Inputs in;
  size_t k = 0;
  const uint32_t dtMs = 1000 / cfg::CONTROL_HZ;
  for (gMs = 0; gMs <= endMs; gMs += dtMs) {
    in.ms = gMs;
    in.tReal = t0 + gMs / 1000.0;
    in.btnHome = in.btnMode = in.btnStow = in.encoderPress = false;
    in.encoderDelta = 0;
    while (k < steps.size() && steps[k].ms <= gMs) {
      const Step& s = steps[k++];
      if (s.op == "BOOT") c.bootDone(in);
      else if (s.op == "CMD") c.command(s.arg.c_str());
      else if (s.op == "ESTOP") in.estop = atoi(s.arg.c_str()) != 0;
      else if (s.op == "LIMAZ") in.limAz = atoi(s.arg.c_str()) != 0;
      else if (s.op == "LIMEL") in.limEl = atoi(s.arg.c_str()) != 0;
      else if (s.op == "BTN") {
        if (s.arg == "HOME") in.btnHome = true;
        else if (s.arg == "MODE") in.btnMode = true;
        else if (s.arg == "STOW") in.btnStow = true;
        else if (s.arg == "ENC") in.encoderPress = true;
      } else if (s.op == "ENC") in.encoderDelta = atoi(s.arg.c_str());
      else if (s.op == "POT") in.potFrac = atof(s.arg.c_str());
      else if (s.op == "TLEFAIL") c.tleDownloadFailed(atol(s.arg.c_str()), in.tReal);
      else if (s.op == "IMU") {
        if (s.arg == "OFF") in.imuOk = false;
        else {
          in.imuOk = true;
          sscanf(s.arg.c_str(), "%lf %lf %lf %lf %lf", &in.ax, &in.ay, &in.az, &in.gx, &in.gy);
        }
      }
    }
    in.azSteps = (long)az.position();
    in.elSteps = (long)el.position();
    const ctl::Outputs& o = c.update(in);
    // apply outputs like main.cpp does with AccelStepper
    az.enabled = el.enabled = o.driversEnabled;
    if (o.stopNow) {
      az.stopNow();
      el.stopNow();
    }
    if (o.az.maxSpeedDps > 0) az.setLimits(o.az.maxSpeedDps, o.az.accelDps2);
    if (o.el.maxSpeedDps > 0) el.setLimits(o.el.maxSpeedDps, o.el.accelDps2);
    if (o.az.setPos) az.setPosition(o.az.target);
    else az.moveTo(o.az.target);
    if (o.el.setPos) el.setPosition(o.el.target);
    else el.moveTo(o.el.target);
    for (uint32_t i = 0; i < dtMs; i++) {
      az.run(0.001);
      el.run(0.001);
    }
  }
  return 0;
}

int main(int argc, char** argv) {
  if (argc < 2) {
    fprintf(stderr, "usage: harness math|parse|scenario < input\n");
    return 2;
  }
  if (!strcmp(argv[1], "math")) return runMath();
  if (!strcmp(argv[1], "parse")) return runParse();
  if (!strcmp(argv[1], "scenario")) return runScenario();
  if (!strcmp(argv[1], "sgp4ver")) return runSgp4Ver();
  return 2;
}
