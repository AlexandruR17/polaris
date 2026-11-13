// Axis position controller: two-degree-of-freedom PID with velocity output.
// Mirror of polaris_gs/core/control.py (same operations in the same order).
//
//   e  = r - y                                   tracking error, axis frame [deg]
//   ff = Kff * r'        r' low-pass filtered (tau_r)        feed-forward [deg/s]
//   P  = Kp * e
//   D  = -Kd * y'        on the measurement, low-pass (tau_d): no kick when r jumps
//   v  = ff + P + I + D                          unsaturated command [deg/s]
//   u  = sat(v): |u| <= vmax, |u - u_prev| <= amax * dt      actuator limits
//   I += Ki * e * dt + Kt * (u - v) * dt         back-calculation anti-windup
//
// The plant seen by this loop is the stepper axis in speed mode: an
// integrator (y' = u) with an acceleration limit. Backward Euler, sample time
// dt = the control period.
#pragma once

namespace ctrl {

struct Gains {
  double kp = 0;   // 1/s
  double ki = 0;   // 1/s^2
  double kd = 0;   // s
  double kff = 1;  // feed-forward weight (0 or 1)
};

struct Terms {
  double e = 0, ff = 0, p = 0, i = 0, d = 0, u = 0;
};

class AxisPid {
 public:
  void configure(const Gains& g, double vmax, double amax, double tauR, double tauD, double kt) {
    g_ = g;
    vmax_ = vmax;
    amax_ = amax;
    tauR_ = tauR;
    tauD_ = tauD;
    kt_ = kt;
  }
  void setGains(const Gains& g) { g_ = g; }
  const Gains& gains() const { return g_; }
  const Terms& terms() const { return t_; }

  // bumpless start: no integral, no rate history, actuator at rest
  void reset(double r, double y) {
    rPrev_ = r;
    yPrev_ = y;
    rDot_ = 0;
    t_ = Terms{};
    t_.e = r - y;
  }

  double update(double r, double y, double dt) {
    t_.e = r - y;
    rDot_ += dt / (tauR_ + dt) * ((r - rPrev_) / dt - rDot_);
    t_.d += dt / (tauD_ + dt) * (-g_.kd * (y - yPrev_) / dt - t_.d);
    rPrev_ = r;
    yPrev_ = y;
    t_.ff = g_.kff * rDot_;
    t_.p = g_.kp * t_.e;
    const double v = t_.ff + t_.p + t_.i + t_.d;
    double u = v;
    if (u > vmax_) u = vmax_;
    if (u < -vmax_) u = -vmax_;
    const double du = amax_ * dt;
    if (u > t_.u + du) u = t_.u + du;
    if (u < t_.u - du) u = t_.u - du;
    t_.i += g_.ki * t_.e * dt + kt_ * (u - v) * dt;
    t_.u = u;
    return u;
  }

 private:
  Gains g_;
  Terms t_;
  double vmax_ = 1, amax_ = 1, tauR_ = 0.1, tauD_ = 0.05, kt_ = 1;
  double rPrev_ = 0, yPrev_ = 0, rDot_ = 0;
};

}  // namespace ctrl
