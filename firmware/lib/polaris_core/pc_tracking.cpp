#include "pc_tracking.h"

#include <math.h>

namespace trk {

// Python round() rounds half to even; nearbyint does the same by default
double unwrapNear(double ref, double az) { return az + 360.0 * nearbyint((ref - az) / 360.0); }

void unwrapSequence(double* az, int n) {
  for (int i = 1; i < n; i++) az[i] = unwrapNear(az[i - 1], az[i]);
}

double planWrap(const double* seq, int n, double currentAz, double azMin, double azMax, bool& ok) {
  double lo = seq[0], hi = seq[0];
  for (int i = 1; i < n; i++) {
    if (seq[i] < lo) lo = seq[i];
    if (seq[i] > hi) hi = seq[i];
  }
  bool found = false;
  double bestOff = 0, bestCost = 0;
  for (int k = -3; k <= 3; k++) {
    const double off = 360.0 * k;
    if (lo + off < azMin - 1e-9 || hi + off > azMax + 1e-9) continue;
    const double cost = fabs(seq[0] + off - currentAz);
    if (!found || cost < bestCost - 1e-9) {
      found = true;
      bestOff = off;
      bestCost = cost;
    }
  }
  ok = found;
  if (!found) return unwrapNear(currentAz, seq[0]) - seq[0];
  return bestOff;
}

void rateLimitFwdBwd(const double* in, double* out, double* tmp, int n, double dt, double maxRate) {
  if (n <= 0) return;
  const double step = maxRate * dt;
  tmp[0] = in[0];
  for (int i = 1; i < n; i++) tmp[i] = tmp[i - 1] + clamp(in[i] - tmp[i - 1], -step, step);
  out[n - 1] = in[n - 1];
  for (int i = n - 2; i >= 0; i--) out[i] = out[i + 1] + clamp(in[i] - out[i + 1], -step, step);
  for (int i = 0; i < n; i++) out[i] = 0.5 * (tmp[i] + out[i]);
}

double maxRate(const double* v, int n, double dt) {
  double m = 0;
  for (int i = 1; i < n; i++) {
    const double r = fabs(v[i] - v[i - 1]) / dt;
    if (r > m) m = r;
  }
  return m;
}

}  // namespace trk
