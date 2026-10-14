// Cable wrap and keyhole planning. Mirror of polaris_gs/core/tracking.py.
#pragma once

namespace trk {

// Equivalent of az (+k*360) closest to ref
double unwrapNear(double ref, double az);

// Unwrap a sequence in place so that consecutive values are continuous
void unwrapSequence(double* az, int n);

// 360 deg offset that keeps the unwrapped pass inside [azMin, azMax] with
// the start closest to currentAz. ok = false if the pass does not fit.
double planWrap(const double* unwrapped, int n, double currentAz, double azMin, double azMax,
                bool& ok);

// Zero-phase rate limit: mean of forward and backward limited profiles.
void rateLimitFwdBwd(const double* in, double* out, double* tmp, int n, double dt,
                     double maxRate);

double maxRate(const double* v, int n, double dt);

inline double clamp(double v, double lo, double hi) { return v < lo ? lo : (v > hi ? hi : v); }

}  // namespace trk
