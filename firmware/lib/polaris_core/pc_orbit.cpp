#include "pc_orbit.h"

#include "pc_config.h"

#include <math.h>
#include <string.h>

#include <stdlib.h>

// Official Vallado SGP4, revision 2020-07-13 (lib/sgp4_vallado)
#include "SGP4.h"

namespace orbit {

static constexpr double WGS84_A = 6378.137;
static constexpr double WGS84_F = 1.0 / 298.257223563;
static constexpr double UNIX_JD0 = 2440587.5;
static constexpr double TWO_PI = 6.283185307179586;

struct Satellite::Impl {
  elsetrec rec;
};

double unixToJd(double t) { return t / 86400.0 + UNIX_JD0; }

double gmstRad(double jdUt1) {
  const double tut1 = (jdUt1 - 2451545.0) / 36525.0;
  double temp = -6.2e-6 * tut1 * tut1 * tut1 + 0.093104 * tut1 * tut1 +
                (876600.0 * 3600.0 + 8640184.812866) * tut1 + 67310.54841;
  temp = fmod(temp * geo::D2R / 240.0, TWO_PI);
  if (temp < 0.0) temp += TWO_PI;
  return temp;
}

bool tleChecksumOk(const char* line) {
  if (strlen(line) < 69) return false;
  int s = 0;
  for (int i = 0; i < 68; i++) {
    const char c = line[i];
    if (c >= '0' && c <= '9') s += c - '0';
    else if (c == '-') s += 1;
  }
  return (s % 10) == (line[68] - '0');
}

Satellite::Satellite()
    : impl_(new Impl()), ready_(false), catnr_(0), name_{0}, epochUnix_(0),
      meanMotionRevDay_(0), lat_(0), lon_(0), site_{0, 0, 0} {
  setSite(cfg::STATION_LAT_DEG, cfg::STATION_LON_DEG, cfg::STATION_ALT_M);
}

Satellite::~Satellite() { delete impl_; }

// Fixed column field of a TLE line as a number ("" -> 0)
static double field(const char* line, int a, int b) {
  char buf[24];
  int k = 0;
  for (int i = a; i < b && line[i] && k < 23; i++) buf[k++] = line[i];
  buf[k] = 0;
  return atof(buf);
}

// Mantissa with implied leading decimal point and exponent, e.g. " 97292-4"
static double impliedExp(const char* line, int a) {
  char buf[16];
  int k = 0;
  buf[k++] = line[a] == '-' ? '-' : '+';
  buf[k++] = '.';
  for (int i = a + 1; i < a + 6; i++) buf[k++] = line[i] == ' ' ? '0' : line[i];
  buf[k] = 0;
  const double m = atof(buf);
  const int e = (int)field(line, a + 6, a + 8);
  return m * pow(10.0, e);
}

bool Satellite::init(const char* name, const char* line1, const char* line2, bool checksum) {
  ready_ = false;
  if (strlen(line1) < 64 || strlen(line2) < 63) return false;
  if (checksum && (!tleChecksumOk(line1) || !tleChecksumOk(line2))) return false;
  if (line1[0] != '1' || line2[0] != '2') return false;
  // same field layout and unit conversion as Vallado twoline2rv
  const double xpdotp = 1440.0 / TWO_PI;
  char satn[6];
  memcpy(satn, line1 + 2, 5);
  satn[5] = 0;
  const int epochyr = (int)field(line1, 18, 20);
  const double epochdays = field(line1, 20, 32);
  const double ndot = field(line1, 33, 43) / (xpdotp * 1440.0);
  const double nddot = impliedExp(line1, 44) / (xpdotp * 1440.0 * 1440.0);
  const double bstar = impliedExp(line1, 53);
  const double inclo = field(line2, 8, 16) * geo::D2R;
  const double nodeo = field(line2, 17, 25) * geo::D2R;
  char ecc[12] = "0.";
  for (int i = 0; i < 7; i++) ecc[2 + i] = line2[26 + i] == ' ' ? '0' : line2[26 + i];
  ecc[9] = 0;
  const double ecco = atof(ecc);
  const double argpo = field(line2, 34, 42) * geo::D2R;
  const double mo = field(line2, 43, 51) * geo::D2R;
  const double noKozai = field(line2, 52, 63) / xpdotp;

  const int year = epochyr < 57 ? epochyr + 2000 : epochyr + 1900;
  int mon, day, hr, minute;
  double sec, jd, jdFrac;
  SGP4Funcs::days2mdhms_SGP4(year, epochdays, mon, day, hr, minute, sec);
  SGP4Funcs::jday_SGP4(year, mon, day, hr, minute, sec, jd, jdFrac);
  elsetrec& rec = impl_->rec;
  memset(&rec, 0, sizeof(rec));
  rec.epochyr = epochyr;
  rec.epochdays = epochdays;
  rec.jdsatepoch = jd;
  rec.jdsatepochF = jdFrac;
  if (!SGP4Funcs::sgp4init(wgs72, 'i', satn, jd + jdFrac - 2433281.5, bstar, ndot, nddot, ecco,
                           argpo, inclo, mo, noKozai, nodeo, rec) ||
      rec.error != 0)
    return false;
  strncpy(name_, name, sizeof(name_) - 1);
  name_[sizeof(name_) - 1] = 0;
  catnr_ = atol(satn);
  epochUnix_ = ((jd - UNIX_JD0) + jdFrac) * 86400.0;
  meanMotionRevDay_ = field(line2, 52, 63);
  ready_ = true;
  return true;
}

void Satellite::setSite(double latDeg, double lonDeg, double altM) {
  lat_ = latDeg;
  lon_ = lonDeg;
  const double lat = latDeg * geo::D2R, lon = lonDeg * geo::D2R;
  const double e2 = WGS84_F * (2.0 - WGS84_F);
  const double n = WGS84_A / sqrt(1.0 - e2 * sin(lat) * sin(lat));
  const double h = altM / 1000.0;
  site_[0] = (n + h) * cos(lat) * cos(lon);
  site_[1] = (n + h) * cos(lat) * sin(lon);
  site_[2] = (n * (1.0 - e2) + h) * sin(lat);
}

bool Satellite::isGeo() const { return fabs(meanMotionRevDay_ - 1.0027) < 0.05; }

bool Satellite::look(double tUnix, Look& out) const {
  if (!ready_) return false;
  double r[3], v[3];
  const double tsince = (tUnix - epochUnix_) / 60.0;
  elsetrec& rec = impl_->rec;
  SGP4Funcs::sgp4(rec, tsince, r, v);
  if (rec.error != 0) {
    rec.error = 0;
    return false;
  }
  const double g = gmstRad(unixToJd(tUnix));
  const double cg = cos(g), sg = sin(g);
  const double ex = cg * r[0] + sg * r[1];
  const double ey = -sg * r[0] + cg * r[1];
  const double ez = r[2];
  const double dx = ex - site_[0], dy = ey - site_[1], dz = ez - site_[2];
  const double lat = lat_ * geo::D2R, lon = lon_ * geo::D2R;
  const double sl = sin(lat), cl = cos(lat), so = sin(lon), co = cos(lon);
  const double e = -so * dx + co * dy;
  const double n = -sl * co * dx - sl * so * dy + cl * dz;
  const double u = cl * co * dx + cl * so * dy + sl * dz;
  const double rng = sqrt(e * e + n * n + u * u);
  double az = atan2(e, n) * geo::R2D;
  if (az < 0) az += 360.0;
  out.az = az;
  out.el = asin(u / rng) * geo::R2D;
  out.rangeKm = rng;
  out.enu = {e / rng, n / rng, u / rng};
  return true;
}

bool Satellite::teme(double tsinceMin, double r[3], double v[3]) const {
  if (!ready_) return false;
  elsetrec& rec = impl_->rec;
  SGP4Funcs::sgp4(rec, tsinceMin, r, v);
  if (rec.error != 0) {
    rec.error = 0;
    return false;
  }
  return true;
}

double Satellite::elevation(double tUnix) const {
  Look l;
  if (!look(tUnix, l)) return -90.0;
  return l.el;
}

double Satellite::bisect(double tBelow, double tAbove, double mask) const {
  for (int i = 0; i < 40; i++) {
    if (fabs(tAbove - tBelow) < 0.5) break;
    const double m = 0.5 * (tBelow + tAbove);
    if (elevation(m) > mask) tAbove = m;
    else tBelow = m;
  }
  return tAbove;
}

void Satellite::maxEl(double a, double b, double& t, double& el) const {
  const double g = 0.6180339887498949;
  double x1 = b - g * (b - a), x2 = a + g * (b - a);
  double f1 = elevation(x1), f2 = elevation(x2);
  for (int i = 0; i < 40; i++) {
    if (b - a < 1.0) break;
    if (f1 < f2) {
      a = x1;
      x1 = x2;
      f1 = f2;
      x2 = a + g * (b - a);
      f2 = elevation(x2);
    } else {
      b = x2;
      x2 = x1;
      f2 = f1;
      x1 = b - g * (b - a);
      f1 = elevation(x1);
    }
  }
  t = 0.5 * (a + b);
  el = elevation(t);
}

double Satellite::findSet(double t0, double horizonS, double mask) const {
  double t = t0;
  while (t < t0 + horizonS) {
    const double t2 = t + 20.0;
    if (elevation(t2) <= mask) {
      double lo = t2, hi = t;
      for (int i = 0; i < 40; i++) {
        if (fabs(lo - hi) < 0.5) break;
        const double m = 0.5 * (lo + hi);
        if (elevation(m) > mask) hi = m;
        else lo = m;
      }
      return hi;
    }
    t = t2;
  }
  return -1.0;
}

Pass Satellite::nextPass(double t0, double horizonH, double mask) const {
  PassSearch s;
  s.begin(this, t0, horizonH, mask);
  while (!s.step(1 << 30)) {
  }
  return s.result();
}

void PassSearch::begin(const Satellite* sat, double t0, double horizonH, double maskDeg) {
  sat_ = sat;
  t0_ = t0;
  horizonS_ = horizonH * 3600.0;
  mask_ = maskDeg;
  result_ = Pass{};
  result_.valid = false;
  phase_ = (sat && sat->ready()) ? START : DONE;
}

bool PassSearch::step(int budget) {
  if (phase_ == DONE) return true;
  const Satellite& s = *sat_;
  if (phase_ == REFINE) {
    Look la;
    s.look(aos_, la);
    result_.valid = true;
    result_.aos = aos_;
    result_.aosAz = la.az;
    const double los = s.findSet(aos_ > t0_ ? aos_ : t0_, horizonS_, mask_);
    if (los < 0) {
      result_.sets = false;
      result_.los = 0;
      result_.tmax = t0_;
      result_.maxEl = s.elevation(t0_);
    } else {
      result_.sets = true;
      result_.los = los;
      s.maxEl(aos_, los, result_.tmax, result_.maxEl);
    }
    phase_ = DONE;
    return true;
  }
  if (phase_ == START) {
    const double el0 = s.elevation(t0_);
    budget--;
    if (s.isGeo()) {
      // geostationary: visible all the time or never, no search needed
      if (el0 > mask_) {
        Look l;
        s.look(t0_, l);
        result_.valid = true;
        result_.aos = t0_;
        result_.aosAz = l.az;
        result_.sets = false;
        result_.los = 0;
        result_.tmax = t0_;
        result_.maxEl = el0;
      }
      phase_ = DONE;
      return true;
    }
    t_ = t0_;
    prev_ = el0;
    phase_ = el0 > mask_ ? BACK : FWD;
  }
  // pass in progress: walk back to AOS (max 30 min)
  while (phase_ == BACK && budget > 0) {
    if (t_ <= t0_ - 1800.0) {
      aos_ = t_;
      phase_ = REFINE;
      break;
    }
    const double t2 = t_ - 20.0;
    budget--;
    if (s.elevation(t2) <= mask_) {
      aos_ = s.bisect(t2, t_, mask_);
      phase_ = REFINE;
      break;
    }
    t_ = t2;
  }
  while (phase_ == FWD && budget > 0) {
    if (t_ >= t0_ + horizonS_) {
      phase_ = DONE;
      return true;
    }
    const double t2 = t_ + (prev_ < -10.0 ? 60.0 : 20.0);
    const double e2 = s.elevation(t2);
    budget--;
    if (e2 > mask_) {
      aos_ = s.bisect(t_, t2, mask_);
      phase_ = REFINE;
      break;
    }
    t_ = t2;
    prev_ = e2;
  }
  return false;
}

}  // namespace orbit
