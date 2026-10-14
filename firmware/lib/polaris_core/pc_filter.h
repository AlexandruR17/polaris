// Complementary filter for roll/pitch from MPU6050.
// Accelerometer in g, gyro in deg/s, sensor axes aligned with the vehicle
// FLU frame (x forward, y left, z up).
#pragma once

#include "pc_geometry.h"

class ComplementaryFilter {
 public:
  explicit ComplementaryFilter(double alpha) : alpha_(alpha) {}

  void reset() { init_ = false; }

  void update(double ax, double ay, double az, double gx, double gy, double dt) {
    double rAcc, pAcc;
    geo::accelToRollPitch(ax, ay, az, rAcc, pAcc);
    if (!init_ || dt <= 0 || dt > 0.5) {
      roll_ = rAcc;
      pitch_ = pAcc;
      init_ = true;
      return;
    }
    // gyro x = roll rate, gyro y = pitch rate (small angle approximation)
    roll_ = alpha_ * (roll_ + gx * dt) + (1.0 - alpha_) * rAcc;
    pitch_ = alpha_ * (pitch_ + gy * dt) + (1.0 - alpha_) * pAcc;
  }

  double roll() const { return roll_; }
  double pitch() const { return pitch_; }

 private:
  double alpha_;
  bool init_ = false;
  double roll_ = 0;
  double pitch_ = 0;
};
