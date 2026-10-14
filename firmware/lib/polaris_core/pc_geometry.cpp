#include "pc_geometry.h"

#include <math.h>

namespace geo {

static Mat3 matMul(const Mat3& a, const Mat3& b) {
  Mat3 r{};
  for (int i = 0; i < 3; i++)
    for (int j = 0; j < 3; j++) {
      double s = 0;
      for (int k = 0; k < 3; k++) s += a.m[i][k] * b.m[k][j];
      r.m[i][j] = s;
    }
  return r;
}

Mat3 attitudeMatrix(double rollDeg, double pitchDeg, double yawDeg) {
  const double r = rollDeg * D2R, p = pitchDeg * D2R, y = yawDeg * D2R;
  const double cr = cos(r), sr = sin(r), cp = cos(p), sp = sin(p), cy = cos(y), sy = sin(y);
  const Mat3 rx{{{1, 0, 0}, {0, cr, -sr}, {0, sr, cr}}};
  const Mat3 ry{{{cp, 0, sp}, {0, 1, 0}, {-sp, 0, cp}}};
  const Mat3 rz{{{cy, -sy, 0}, {sy, cy, 0}, {0, 0, 1}}};
  return matMul(matMul(rz, ry), rx);
}

Vec3 mul(const Mat3& a, const Vec3& v) {
  return {a.m[0][0] * v.x + a.m[0][1] * v.y + a.m[0][2] * v.z,
          a.m[1][0] * v.x + a.m[1][1] * v.y + a.m[1][2] * v.z,
          a.m[2][0] * v.x + a.m[2][1] * v.y + a.m[2][2] * v.z};
}

Vec3 mulT(const Mat3& a, const Vec3& v) {
  return {a.m[0][0] * v.x + a.m[1][0] * v.y + a.m[2][0] * v.z,
          a.m[0][1] * v.x + a.m[1][1] * v.y + a.m[2][1] * v.z,
          a.m[0][2] * v.x + a.m[1][2] * v.y + a.m[2][2] * v.z};
}

Vec3 azelToEnu(double azDeg, double elDeg) {
  const double az = azDeg * D2R, el = elDeg * D2R;
  return {cos(el) * sin(az), cos(el) * cos(az), sin(el)};
}

AzEl enuToAzel(const Vec3& v) {
  double az = atan2(v.x, v.y) * R2D;
  if (az < 0) az += 360.0;
  return {az, atan2(v.z, hypot(v.x, v.y)) * R2D};
}

Vec3 enuToBody(const Vec3& v, double roll, double pitch, double yaw) {
  return mulT(attitudeMatrix(roll, pitch, yaw), v);
}

Vec3 bodyToEnu(const Vec3& v, double roll, double pitch, double yaw) {
  return mul(attitudeMatrix(roll, pitch, yaw), v);
}

AzEl bodyToPedestal(const Vec3& v) {
  return {wrap180(atan2(-v.y, v.x) * R2D), atan2(v.z, hypot(v.x, v.y)) * R2D};
}

Vec3 pedestalToBody(double azDeg, double elDeg) {
  const double az = azDeg * D2R, el = elDeg * D2R;
  return {cos(el) * cos(az), -cos(el) * sin(az), sin(el)};
}

AzEl pointingCommand(const Vec3& satEnu, double roll, double pitch, double yaw, bool compensate) {
  if (!compensate) {
    roll = 0;
    pitch = 0;
  }
  return bodyToPedestal(enuToBody(satEnu, roll, pitch, yaw));
}

double angleBetween(const Vec3& a, const Vec3& b) {
  const double na = sqrt(a.x * a.x + a.y * a.y + a.z * a.z);
  const double nb = sqrt(b.x * b.x + b.y * b.y + b.z * b.z);
  const double c = (a.x * b.x + a.y * b.y + a.z * b.z) / (na * nb);
  const Vec3 x{a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
  const double s = sqrt(x.x * x.x + x.y * x.y + x.z * x.z) / (na * nb);
  return atan2(s, c) * R2D;
}

double pointingError(double pedAz, double pedEl, double roll, double pitch, double yaw,
                     const Vec3& satEnu) {
  return angleBetween(bodyToEnu(pedestalToBody(pedAz, pedEl), roll, pitch, yaw), satEnu);
}

double wrap180(double a) {
  a = fmod(a + 180.0, 360.0);
  if (a < 0) a += 360.0;
  return a - 180.0;
}

void accelToRollPitch(double ax, double ay, double az, double& rollDeg, double& pitchDeg) {
  rollDeg = atan2(ay, az) * R2D;
  pitchDeg = atan2(-ax, hypot(ay, az)) * R2D;
}

}  // namespace geo
