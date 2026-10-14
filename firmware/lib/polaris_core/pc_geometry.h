// Frames and pointing geometry. Mirror of polaris_gs/core/geometry.py.
// World: ENU. Vehicle: FLU (x forward, y left, z up), ROS REP-103.
// R = Rz(yaw) * Ry(pitch) * Rx(roll), body = R^T * enu.
// Pedestal azimuth: 0 = vehicle forward, positive clockwise from above.
#pragma once

namespace geo {

struct Vec3 {
  double x, y, z;
};

struct Mat3 {
  double m[3][3];
};

struct AzEl {
  double az, el;
};

constexpr double D2R = 0.017453292519943295;
constexpr double R2D = 57.29577951308232;

Mat3 attitudeMatrix(double rollDeg, double pitchDeg, double yawDeg);
Vec3 mul(const Mat3& a, const Vec3& v);
Vec3 mulT(const Mat3& a, const Vec3& v);

Vec3 azelToEnu(double azDeg, double elDeg);
AzEl enuToAzel(const Vec3& v);  // az in [0, 360)

Vec3 enuToBody(const Vec3& v, double roll, double pitch, double yaw);
Vec3 bodyToEnu(const Vec3& v, double roll, double pitch, double yaw);
AzEl bodyToPedestal(const Vec3& v);  // az in [-180, 180)
Vec3 pedestalToBody(double azDeg, double elDeg);

// Pedestal angles that point at a satellite. Without compensation the
// vehicle is assumed level, only yaw is used.
AzEl pointingCommand(const Vec3& satEnu, double roll, double pitch, double yaw, bool compensate);
double angleBetween(const Vec3& a, const Vec3& b);
double pointingError(double pedAz, double pedEl, double roll, double pitch, double yaw,
                     const Vec3& satEnu);

double wrap180(double a);
void accelToRollPitch(double ax, double ay, double az, double& rollDeg, double& pitchDeg);

}  // namespace geo
