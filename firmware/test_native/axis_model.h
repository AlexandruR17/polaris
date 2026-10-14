// Continuous model of AccelStepper run(). Port of polaris_gs/core/tracking.py Axis.
// Used only by the native harness; the firmware drives AccelStepper.
#pragma once

#include <math.h>

#include "pc_config.h"

struct AxisModel {
  double pos = 0, speed = 0, target = 0;
  double maxSpeed = 0, accel = 1;
  bool enabled = true;

  void setLimits(double vDps, double aDps2) {
    maxSpeed = vDps * cfg::STEPS_PER_DEG;
    accel = aDps2 * cfg::STEPS_PER_DEG;
  }
  void moveTo(double steps) { target = nearbyint(steps); }
  void stopNow() {
    speed = 0;
    target = position();
  }
  void setPosition(double steps) {
    pos = steps;
    target = steps;
    speed = 0;
  }
  double position() const { return nearbyint(pos); }

  void run(double dt) {
    if (!enabled) {
      speed = 0;
      return;
    }
    const double dist = target - pos;
    if (fabs(dist) < 0.5 && fabs(speed) < accel * dt * 2) {
      pos = target;
      speed = 0;
      return;
    }
    const double stopDist = speed * speed / (2.0 * accel);
    const bool away = speed * dist < 0;
    if (away || fabs(dist) <= stopDist) {
      const double dv = accel * dt;
      if (fabs(speed) <= dv) speed = 0;
      else speed -= copysign(dv, speed);
      if (!away && speed == 0.0) speed = copysign(fmin(accel * dt, maxSpeed), dist);
    } else {
      speed += copysign(accel * dt, dist);
      if (speed > maxSpeed) speed = maxSpeed;
      if (speed < -maxSpeed) speed = -maxSpeed;
    }
    double nw = pos + speed * dt;
    if ((target - pos) * (target - nw) < 0 && !away) {
      nw = target;
      speed = 0;
    }
    pos = nw;
  }
};
