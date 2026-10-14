// SGP4 propagation, look angles and pass prediction.
// Mirror of polaris_gs/core/orbit.py. Uses the official Vallado SGP4
// (revision 2020-07-13, lib/sgp4_vallado), WGS72 constants, improved mode.
#pragma once

#include <stdint.h>

#include "pc_geometry.h"

namespace orbit {

struct Look {
  double az, el, rangeKm;
  geo::Vec3 enu;  // unit vector
};

struct Pass {
  bool valid;
  double aos;
  double los;  // valid only when sets == true
  bool sets;   // false: geostationary, never sets
  double tmax;
  double maxEl;
  double aosAz;
};

double unixToJd(double t);
double gmstRad(double jdUt1);

class Satellite {
 public:
  Satellite();
  ~Satellite();
  Satellite(const Satellite&) = delete;
  Satellite& operator=(const Satellite&) = delete;

  // Returns false on a bad TLE (checksum or SGP4 init error)
  bool init(const char* name, const char* line1, const char* line2, bool checksum = true);
  void setSite(double latDeg, double lonDeg, double altM);

  bool look(double tUnix, Look& out) const;
  // Raw SGP4 state in TEME (km, km/s), minutes since epoch
  bool teme(double tsinceMin, double r[3], double v[3]) const;
  double elevation(double tUnix) const;
  Pass nextPass(double t0, double horizonH, double maskDeg) const;

  bool ready() const { return ready_; }
  long catnr() const { return catnr_; }
  const char* name() const { return name_; }
  double epochUnix() const { return epochUnix_; }
  double ageDays(double tUnix) const { return (tUnix - epochUnix_) / 86400.0; }
  bool isGeo() const;

 private:
  double bisect(double tBelow, double tAbove, double mask) const;
  double findSet(double t0, double horizonS, double mask) const;
  void maxEl(double a, double b, double& t, double& el) const;

  struct Impl;
  Impl* impl_;
  bool ready_;
  long catnr_;
  char name_[25];
  double epochUnix_;
  double meanMotionRevDay_;
  double lat_, lon_;
  double site_[3];
};

bool tleChecksumOk(const char* line);

}  // namespace orbit
