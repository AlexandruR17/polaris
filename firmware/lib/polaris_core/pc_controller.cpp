#include "pc_controller.h"

#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "pc_geometry.h"
#include "pc_tracking.h"

namespace ctl {

using namespace cfg;

const long SAT_IDS[NUM_SATS] = {25544, 33591, 28654, 43700};

float Controller::planLead_[PASS_MAX_SAMPLES];
float Controller::planAz_[PASS_MAX_SAMPLES];
double Controller::work0_[PASS_MAX_SAMPLES];
double Controller::work1_[PASS_MAX_SAMPLES];
double Controller::work2_[PASS_MAX_SAMPLES];

static const char* STATE_NAMES[] = {"BOOT",  "HOMING", "IDLE",   "WAIT_AOS", "ACQUIRE", "TRACK",
                                    "STOW",  "MANUAL", "DEMO",   "ESTOP",    "FAULT"};
static const char* MODE_NAMES[] = {"AUTO", "MANUAL", "DEMO", "IDLE", "STOW"};

const char* stateName(State s) { return STATE_NAMES[(int)s]; }
const char* modeName(Mode m) { return MODE_NAMES[(int)m]; }

static long toSteps(double deg) { return (long)nearbyint(deg * STEPS_PER_DEG); }

Controller::Controller() : satId_(DEFAULT_SAT), filter_(COMP_FILTER_ALPHA) {
  for (int i = 0; i < NUM_SATS; i++) {
    memset(&slots_[i], 0, sizeof(SatSlot));
    slots_[i].catnr = SAT_IDS[i];
  }
}

void Controller::begin(bool simLimits, EmitFn emitFn, void* ctx) {
  simLimits_ = simLimits;
  emitFn_ = emitFn;
  emitCtx_ = ctx;
  state_ = State::BOOT;
  emitf("{\"ev\":\"BOOT\",\"fw\":\"%s\",\"sim\":%d}", FW_VERSION, simLimits ? 1 : 0);
}

// ---------------------------------------------------------------- output
void Controller::emit(const char* line) {
  if (emitFn_) emitFn_(emitCtx_, line);
}

void Controller::emitf(const char* fmt, ...) {
  char buf[400];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  emit(buf);
}

void Controller::setState(State s) {
  if (s == state_) return;
  emitf("{\"ev\":\"MODE\",\"from\":\"%s\",\"to\":\"%s\"}", stateName(state_), stateName(s));
  state_ = s;
}

// ---------------------------------------------------------------- TLE / satellite
int Controller::slotIndex(long id) const {
  for (int i = 0; i < NUM_SATS; i++)
    if (slots_[i].catnr == id) return i;
  return -1;
}

bool Controller::tleFallback() const {
  const int i = slotIndex(satId_);
  return i < 0 || slots_[i].fallback;
}

bool Controller::loadTle(long catnr, const char* name, const char* l1, const char* l2,
                         bool fallback, double tNow, bool announce) {
  const int i = slotIndex(catnr);
  if (i < 0) return false;
  orbit::Satellite probe;
  if (!probe.init(name, l1, l2)) {
    emitf("{\"ev\":\"ERR\",\"msg\":\"BAD_TLE\",\"sat\":%ld}", catnr);
    return false;
  }
  SatSlot& s = slots_[i];
  strncpy(s.name, name, sizeof(s.name) - 1);
  strncpy(s.l1, l1, sizeof(s.l1) - 1);
  strncpy(s.l2, l2, sizeof(s.l2) - 1);
  s.loaded = true;
  s.fallback = fallback;
  if (!fallback) s.tried = true;
  if (announce)
    emitf("{\"ev\":\"%s\",\"sat\":%ld,\"age_d\":%.1f}", fallback ? "TLE_FALLBACK" : "TLE_OK",
          catnr, probe.ageDays(tNow));
  if (catnr == satId_) {
    sat_.init(s.name, s.l1, s.l2);
    pass_.valid = false;
    passTried_ = false;
    planValid_ = false;
    refreshLook(true);
    if (announce) emitTle();
  }
  return true;
}

// The exact elements in use, so a ground station can check the same orbit
void Controller::emitTle() {
  const int i = slotIndex(satId_);
  if (i < 0 || !slots_[i].loaded) return;
  char name[sizeof(slots_[i].name)];
  size_t n = 0;
  for (const char* p = slots_[i].name; *p && n + 1 < sizeof(name); p++)
    name[n++] = (*p == '"' || *p == '\\' || (unsigned char)*p < 32) ? '\'' : *p;
  name[n] = 0;
  emitf("{\"ev\":\"TLE\",\"sat\":%ld,\"name\":\"%s\",\"l1\":\"%s\",\"l2\":\"%s\"}", satId_, name,
        slots_[i].l1, slots_[i].l2);
}

void Controller::tleDownloadFailed(long catnr, double tNow) {
  const int i = slotIndex(catnr);
  if (i < 0 || !slots_[i].loaded) return;
  slots_[i].tried = true;
  orbit::Satellite probe;
  probe.init(slots_[i].name, slots_[i].l1, slots_[i].l2);
  emitf("{\"ev\":\"TLE_FALLBACK\",\"sat\":%ld,\"age_d\":%.1f}", catnr, probe.ageDays(tNow));
  if (catnr == satId_) emitTle();
}

void Controller::selectSat(long id) {
  const int i = slotIndex(id);
  satId_ = id;
  SatSlot& s = slots_[i];
  if (s.loaded) sat_.init(s.name, s.l1, s.l2);
  if (s.fallback && !s.tried) {
    pendingTle_ = id;
    s.tried = true;
  }
  pass_.valid = false;
  passTried_ = false;
  planValid_ = false;
  refreshLook(true);
  if (demo_) endDemo();
  if (state_ == State::ACQUIRE || state_ == State::TRACK || state_ == State::WAIT_AOS ||
      state_ == State::DEMO) {
    mode_ = Mode::AUTO;
    enterWaitAos();
  }
  emitTle();
}

// ---------------------------------------------------------------- satellite look
void Controller::refreshLook(bool reset) {
  if (reset) prevValid_ = false;
  orbit::Look l;
  if (!sat_.ready() || !sat_.look(tSim_, l)) {
    lookValid_ = false;
    return;
  }
  if (lookValid_ && !reset) {
    prevEnu_ = look_.enu;
    prevT_ = lookT_;
    prevValid_ = tSim_ > lookT_;
  }
  look_ = l;
  lookT_ = tSim_;
  lookValid_ = true;
}

geo::Vec3 Controller::satEnuAt(double t) const {
  geo::Vec3 v = look_.enu;
  if (prevValid_ && lookT_ > prevT_) {
    double k = (t - lookT_) / (lookT_ - prevT_);
    if (k < 0) k = 0;
    if (k > 2) k = 2;
    v = {v.x + (v.x - prevEnu_.x) * k, v.y + (v.y - prevEnu_.y) * k, v.z + (v.z - prevEnu_.z) * k};
    const double n = sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
    v = {v.x / n, v.y / n, v.z / n};
  }
  return v;
}

// ---------------------------------------------------------------- pass planning
void Controller::computePass(double t) {
  pass_ = sat_.nextPass(t, PASS_SEARCH_H, MASK_EL_DEG);
  passTried_ = true;
  passTryMs_ = ms_;
  planValid_ = false;
  if (!pass_.valid) {
    emitf("{\"ev\":\"INFO\",\"msg\":\"NO_PASS\",\"sat\":%ld}", satId_);
    return;
  }
  char aos[32], los[40];
  proto::isoUtc(pass_.aos, aos, sizeof(aos));
  if (pass_.sets) {
    char tmp[32];
    proto::isoUtc(pass_.los, tmp, sizeof(tmp));
    snprintf(los, sizeof(los), "\"%s\"", tmp);
  } else {
    strcpy(los, "null");
  }
  emitf("{\"ev\":\"PASS\",\"sat\":%ld,\"aos\":\"%s\",\"los\":%s,\"max_el\":%.1f,\"aos_az\":%.1f}",
        satId_, aos, los, pass_.maxEl, pass_.aosAz);
  buildPlan(t, antAz_);
}

void Controller::buildPlan(double tFrom, double refAz) {
  planValid_ = false;
  if (!pass_.valid || !pass_.sets) return;
  const double t0 = pass_.aos > tFrom ? pass_.aos : tFrom;
  const double dur = pass_.los - t0;
  if (dur <= 0) return;
  int n = (int)(dur / PASS_SAMPLE_S) + 1;
  if (n > PASS_MAX_SAMPLES) n = PASS_MAX_SAMPLES;
  if (n < 2) n = 2;
  const double dt = dur / (n - 1);
  double el0 = 0;
  for (int i = 0; i < n; i++) {
    orbit::Look l;
    if (!sat_.look(t0 + i * dt, l)) return;
    const geo::AzEl p = geo::pointingCommand(l.enu, roll_, pitch_, yaw_, comp_);
    work0_[i] = p.az;
    if (i == 0) el0 = p.el;
  }
  trk::unwrapSequence(work0_, n);
  bool ok = true;
  const double off = trk::planWrap(work0_, n, refAz, AZ_MIN_DEG, AZ_MAX_DEG, ok);
  for (int i = 0; i < n; i++) work0_[i] += off;
  if (!ok) emit("{\"ev\":\"INFO\",\"msg\":\"WRAP_UNAVOIDABLE\"}");
  const double w = (double)(demo_ ? warp_ : 1);
  const double vmax = KEYHOLE_PLAN_MARGIN * AZ_MAX_SPEED_DPS / w;
  const double req = trk::maxRate(work0_, n, dt);
  trk::rateLimitFwdBwd(work0_, work1_, work2_, n, dt, vmax);
  for (int i = 0; i < n; i++) {
    planAz_[i] = (float)work0_[i];
    planLead_[i] = (float)(work1_[i] - work0_[i]);
  }
  planN_ = n;
  planT0_ = t0;
  planDt_ = dt;
  planStartAz_ = work1_[0];
  planStartEl_ = trk::clamp(el0, EL_MIN_DEG, EL_MAX_DEG);
  planValid_ = true;
  if (req > vmax) {
    emitf("{\"ev\":\"KEYHOLE\",\"pred\":1,\"req_dps\":%.1f,\"max_dps\":%.1f}", req * w,
          AZ_MAX_SPEED_DPS);
  }
}

static double interpTable(const float* tab, int n, double t0, double dt, double t) {
  double x = (t - t0) / dt;
  if (x <= 0) return tab[0];
  if (x >= n - 1) return tab[n - 1];
  const int i = (int)x;
  const double f = x - i;
  const double a = (double)tab[i], b = (double)tab[i + 1];
  return a + (b - a) * f;
}

double Controller::planLeadAt(double t) const {
  return planValid_ ? interpTable(planLead_, planN_, planT0_, planDt_, t) : 0.0;
}

double Controller::planAzAt(double t) const {
  return interpTable(planAz_, planN_, planT0_, planDt_, t);
}

// ---------------------------------------------------------------- state entries
void Controller::bootDone(const Inputs& in) {
  in_ = in;
  ms_ = in.ms;
  tSim_ = in.tReal;
  if (state_ != State::BOOT) return;
  if (sat_.ready() == false) selectSat(satId_);
  startHoming();
}

void Controller::startHoming() {
  if (demo_) endDemo();
  setState(State::HOMING);
  homeStartMs_ = ms_;
  azHomed_ = elHomed_ = false;
  azStart_ = in_.azSteps;
  elStart_ = in_.elSteps;
  out_.driversEnabled = true;
  out_.relayOn = true;
  setTargets((in_.azSteps / STEPS_PER_DEG) - 720.0, (in_.elSteps / STEPS_PER_DEG) - 200.0,
             HOMING_SPEED_DPS, AZ_ACCEL_DPS2, HOMING_SPEED_DPS, EL_ACCEL_DPS2);
}

void Controller::afterHoming() {
  emitf("{\"ev\":\"HOME_OK\",\"t_s\":%.1f}", (ms_ - homeStartMs_) / 1000.0);
  pendingBeep_ = BEEP_OK;
  applyMode();
}

void Controller::applyMode() {
  if (demo_ && mode_ != Mode::DEMO) endDemo();
  switch (mode_) {
    case Mode::AUTO: enterWaitAos(); break;
    case Mode::MANUAL:
      manAz_ = antAz_;
      manEl_ = antEl_;
      setState(State::MANUAL);
      break;
    case Mode::DEMO: enterDemo(); break;
    case Mode::IDLE:
      cmdAz_ = antAz_;
      cmdEl_ = antEl_;
      setState(State::IDLE);
      break;
    case Mode::STOW: setState(State::STOW); break;
  }
}

void Controller::enterWaitAos() {
  haveRaw_ = false;
  keyhole_ = false;
  setState(State::WAIT_AOS);
  if (!pass_.valid || (pass_.sets && tSim_ > pass_.los)) computePass(tSim_);
}

void Controller::enterTracking() {
  haveRaw_ = false;
  errSum2_ = errMax_ = 0;
  errN_ = 0;
  keyhole_ = false;
  char t[32];
  proto::isoUtc(tSim_, t, sizeof(t));
  emitf("{\"ev\":\"AOS\",\"sat\":%ld,\"t_utc\":\"%s\",\"az\":%.1f,\"el\":%.1f}", satId_, t,
        look_.az, look_.el);
  pendingBeep_ = BEEP_AOS;
  // replan with the attitude we have now, keep continuity with the antenna
  if (pass_.valid && pass_.sets) buildPlan(tSim_, planValid_ ? planAzAt(tSim_) : antAz_);
  setState(State::ACQUIRE);
}

void Controller::enterDemo() {
  setState(State::DEMO);
  orbit::Pass p = sat_.nextPass(in_.tReal, PASS_SEARCH_H, MASK_EL_DEG);
  for (int i = 0; i < 30 && p.valid && p.sets && p.maxEl < DEMO_MIN_MAX_EL_DEG; i++)
    p = sat_.nextPass(p.los + 60.0, PASS_SEARCH_H, MASK_EL_DEG);
  if (!p.valid || !p.sets || p.maxEl < DEMO_MIN_MAX_EL_DEG) {
    emit("{\"ev\":\"ERR\",\"msg\":\"NO_PASS\"}");
    mode_ = Mode::AUTO;
    enterWaitAos();
    return;
  }
  demo_ = true;
  warp_ = demoWarp_;
  anchorSim_ = p.aos - DEMO_LEAD_S;
  anchorMs_ = ms_;
  tSim_ = anchorSim_;
  refreshLook(true);
  emitf("{\"ev\":\"INFO\",\"msg\":\"DEMO\",\"warp\":%d}", warp_);
  computePass(tSim_);
}

void Controller::endDemo() {
  demo_ = false;
  warp_ = 1;
  tSim_ = in_.tReal;
  pass_.valid = false;
  planValid_ = false;
  refreshLook(true);
  emit("{\"ev\":\"INFO\",\"msg\":\"DEMO_END\"}");
}

void Controller::enterEstop() {
  if (demo_) endDemo();
  setState(State::ESTOP);
  emit("{\"ev\":\"ESTOP\"}");
  pendingBeep_ = BEEP_ERROR;
  out_.driversEnabled = false;
  out_.relayOn = false;
  out_.stopNow = true;
  estopReleasedSaid_ = false;
}

void Controller::enterFault(const char* code) {
  if (demo_) endDemo();
  strncpy(fault_, code, sizeof(fault_) - 1);
  setState(State::FAULT);
  emitf("{\"ev\":\"FAULT\",\"code\":\"%s\"}", code);
  pendingBeep_ = BEEP_ERROR;
  out_.driversEnabled = false;
  out_.relayOn = false;
  out_.stopNow = true;
}

void Controller::ack() {
  if (state_ == State::ESTOP) {
    if (in_.estop) {
      emit("{\"ev\":\"ERR\",\"msg\":\"ESTOP_ACTIVE\"}");
      return;
    }
  } else if (state_ == State::FAULT) {
    if (in_.limAz || in_.limEl) {
      emit("{\"ev\":\"ERR\",\"msg\":\"LIMIT_ACTIVE\"}");
      return;
    }
  } else {
    emit("{\"ev\":\"ERR\",\"msg\":\"NOTHING_TO_ACK\"}");
    return;
  }
  emit("{\"ev\":\"ACK\"}");
  fault_[0] = 0;
  startHoming();
}

// ---------------------------------------------------------------- commands
void Controller::command(const char* line) {
  proto::Command c;
  char clean[64];
  proto::sanitize(line, clean, sizeof(clean));
  const char* err = proto::parseCommand(line, c);
  if (err) {
    emitf("{\"ev\":\"ERR\",\"cmd\":\"%s\",\"msg\":\"%s\"}", clean, err);
    return;
  }
  if (c.cmd == proto::Cmd::SAT && slotIndex(c.sat) < 0) {
    emitf("{\"ev\":\"ERR\",\"cmd\":\"%s\",\"msg\":\"unknown sat\"}", clean);
    return;
  }
  if (c.cmd == proto::Cmd::JOG && state_ != State::MANUAL) {
    emitf("{\"ev\":\"ERR\",\"cmd\":\"%s\",\"msg\":\"not manual\"}", clean);
    return;
  }
  emitf("{\"ev\":\"CMD\",\"cmd\":\"%s\"}", clean);
  const bool busy = state_ == State::BOOT || state_ == State::HOMING || state_ == State::ESTOP ||
                    state_ == State::FAULT;
  switch (c.cmd) {
    case proto::Cmd::SAT: selectSat(c.sat); break;
    case proto::Cmd::MODE: {
      for (int i = 0; i < 5; i++)
        if (!strcmp(c.mode, MODE_NAMES[i])) mode_ = (Mode)i;
      if (!busy) applyMode();
      break;
    }
    case proto::Cmd::WARP:
      demoWarp_ = c.warp;
      if (demo_) {
        anchorSim_ = tSim_;
        anchorMs_ = ms_;
        warp_ = c.warp;
        if (state_ == State::ACQUIRE || state_ == State::TRACK)
          buildPlan(tSim_, planValid_ ? planAzAt(tSim_) : cmdAz_);
      }
      break;
    case proto::Cmd::VEH:
      vehActive_ = true;
      vehRoll_ = c.roll;
      vehPitch_ = c.pitch;
      vehYaw_ = c.yaw;
      vehMs_ = ms_;
      break;
    case proto::Cmd::VEH_OFF: vehActive_ = false; break;
    case proto::Cmd::JOG:
      if (c.axis[0] == 'A') manAz_ = trk::clamp(manAz_ + c.jogDeg, AZ_MIN_DEG, AZ_MAX_DEG);
      else manEl_ = trk::clamp(manEl_ + c.jogDeg, EL_MIN_DEG, EL_MAX_DEG);
      break;
    case proto::Cmd::HOME:
      if (state_ == State::ESTOP || state_ == State::FAULT) ack();
      else if (state_ != State::BOOT) startHoming();
      break;
    case proto::Cmd::STOW:
      mode_ = Mode::STOW;
      if (!busy) applyMode();
      break;
    case proto::Cmd::ACK: ack(); break;
    case proto::Cmd::TLE: emitTle(); break;
    case proto::Cmd::COMP:
      comp_ = c.comp;
      if (state_ == State::ACQUIRE || state_ == State::TRACK)
        buildPlan(tSim_, planValid_ ? planAzAt(tSim_) : cmdAz_);
      break;
    default: break;
  }
}

// ---------------------------------------------------------------- periodic
void Controller::updateAttitude(const Inputs& in) {
  if (vehActive_ && (in.ms - vehMs_) > (uint32_t)(VEH_TIMEOUT_S * 1000.0)) vehActive_ = false;
  if (in.imuOk) {
    const double dt = imuSeen_ ? (in.ms - imuMs_) / 1000.0 : 0.0;
    filter_.update(in.ax, in.ay, in.az, in.gx, in.gy, dt);
    imuMs_ = in.ms;
    imuSeen_ = true;
  }
  if (vehActive_) {
    roll_ = vehRoll_;
    pitch_ = vehPitch_;
    yaw_ = vehYaw_;
    src_ = "VEH";
  } else if (imuSeen_) {
    roll_ = filter_.roll();
    pitch_ = filter_.pitch();
    yaw_ = VEHICLE_YAW_DEFAULT_DEG;
    src_ = "MPU";
  } else {
    roll_ = pitch_ = 0;
    yaw_ = VEHICLE_YAW_DEFAULT_DEG;
    src_ = "NONE";
  }
}

void Controller::setTargets(double azDeg, double elDeg, double vAz, double aAz, double vEl,
                            double aEl) {
  cmdAz_ = azDeg;
  cmdEl_ = elDeg;
  out_.az.target = toSteps(azDeg);
  out_.el.target = toSteps(elDeg);
  out_.az.maxSpeedDps = vAz;
  out_.az.accelDps2 = aAz;
  out_.el.maxSpeedDps = vEl;
  out_.el.accelDps2 = aEl;
}

void Controller::pointingTick() {
  const geo::Vec3 enu = satEnuAt(tSim_);
  const geo::AzEl p = geo::pointingCommand(enu, roll_, pitch_, yaw_, comp_);
  if (!haveRaw_) {
    const double ref = planValid_ ? planAzAt(tSim_) : antAz_;
    rawAz_ = trk::unwrapNear(ref, p.az);
    rawMs_ = ms_;
    reqRate_ = 0;
    haveRaw_ = true;
  } else {
    const double nr = trk::unwrapNear(rawAz_, p.az);
    const double dt = (ms_ - rawMs_) / 1000.0;
    if (dt > 0) reqRate_ = fabs(nr - rawAz_) / dt;
    rawAz_ = nr;
    rawMs_ = ms_;
  }
  const double lead = planLeadAt(tSim_);
  double az = rawAz_ + lead;
  if (az > AZ_MAX_DEG || az < AZ_MIN_DEG) {
    const double shift = az > AZ_MAX_DEG ? -360.0 : 360.0;
    emitf("{\"ev\":\"WRAP\",\"from\":%.1f,\"to\":%.1f}", az, az + shift);
    rawAz_ += shift;
    az += shift;
    planValid_ = false;
  }
  az = trk::clamp(az, AZ_MIN_DEG, AZ_MAX_DEG);
  const double el = trk::clamp(p.el, EL_MIN_DEG, EL_MAX_DEG);
  setTargets(az, el, AZ_MAX_SPEED_DPS, AZ_ACCEL_DPS2, EL_MAX_SPEED_DPS, EL_ACCEL_DPS2);

  const bool cond = err_ > KEYHOLE_ERR_DEG &&
                    (fabs(lead) > 0.5 * KEYHOLE_ERR_DEG || reqRate_ > 0.95 * AZ_MAX_SPEED_DPS);
  if (cond != keyhole_ && (ms_ - khMs_) > 1000) {
    keyhole_ = cond;
    khMs_ = ms_;
    // near the zenith the azimuth rate explodes (keyhole); elsewhere a rate
    // limit hit comes from vehicle motion
    if (cond) khZenith_ = look_.el > KEYHOLE_EL_DEG;
    emitf("{\"ev\":\"%s\",\"on\":%d,\"err\":%.2f,\"req_dps\":%.1f}",
          khZenith_ ? "KEYHOLE" : "RATE_LIMIT", cond ? 1 : 0, err_, reqRate_);
  }
}

const Outputs& Controller::update(const Inputs& in) {
  in_ = in;
  ms_ = in.ms;
  out_.az.setPos = false;
  out_.el.setPos = false;
  out_.stopNow = false;
  out_.beep = BEEP_NONE;
  out_.tleRequest = 0;

  // clock
  if (demo_) {
    if (state_ == State::DEMO) {
      anchorMs_ = in.ms;  // frozen while prepositioning
      tSim_ = anchorSim_;
    } else {
      tSim_ = anchorSim_ + warp_ * ((double)(in.ms - anchorMs_)) / 1000.0;
    }
  } else {
    tSim_ = in.tReal;
  }

  antAz_ = in.azSteps / STEPS_PER_DEG;
  antEl_ = in.elSteps / STEPS_PER_DEG;
  updateAttitude(in);

  // safety first
  if (in.estop && state_ != State::ESTOP && state_ != State::BOOT) enterEstop();
  if (!in.limAz) limArmedAz_ = true;
  if (!in.limEl) limArmedEl_ = true;
  const bool limCheck = state_ != State::BOOT && state_ != State::HOMING &&
                        state_ != State::ESTOP && state_ != State::FAULT;
  if (limCheck && in.limAz && limArmedAz_) enterFault("LIMIT_AZ");
  else if (limCheck && in.limEl && limArmedEl_) enterFault("LIMIT_EL");

  // operator buttons
  if (in.btnHome) {
    if (state_ == State::ESTOP || state_ == State::FAULT) ack();
    else if (state_ != State::BOOT) startHoming();
  }
  const bool busy = state_ == State::BOOT || state_ == State::HOMING ||
                    state_ == State::ESTOP || state_ == State::FAULT;
  if (in.btnStow && !busy) {
    mode_ = Mode::STOW;
    applyMode();
  }
  if (in.btnMode && !busy) {
    mode_ = mode_ == Mode::AUTO ? Mode::MANUAL : (mode_ == Mode::MANUAL ? Mode::DEMO : Mode::AUTO);
    applyMode();
  }
  if (in.encoderPress && state_ == State::MANUAL) manAxisEl_ = !manAxisEl_;

  // satellite at SAT_HZ
  if (tick_ % (CONTROL_HZ / SAT_HZ) == 0 || !lookValid_) refreshLook(false);
  if (lookValid_) err_ = geo::pointingError(antAz_, antEl_, roll_, pitch_, yaw_, satEnuAt(tSim_));

  switch (state_) {
    case State::BOOT:
      out_.driversEnabled = false;
      out_.relayOn = false;
      break;

    case State::HOMING: {
      const bool azTrig = in.limAz || (simLimits_ && azStart_ - in.azSteps >= SIM_HOME_AZ_STEPS);
      const bool elTrig = in.limEl || (simLimits_ && elStart_ - in.elSteps >= SIM_HOME_EL_STEPS);
      if (!azHomed_ && azTrig) {
        azHomed_ = true;
        out_.az.target = toSteps(AZ_HOME_DEG);
        out_.az.setPos = true;
        limArmedAz_ = !in.limAz;
      }
      if (!elHomed_ && elTrig) {
        elHomed_ = true;
        out_.el.target = toSteps(EL_HOME_DEG);
        out_.el.setPos = true;
        limArmedEl_ = !in.limEl;
      }
      if (azHomed_ && elHomed_) {
        antAz_ = AZ_HOME_DEG;
        antEl_ = EL_HOME_DEG;
        cmdAz_ = AZ_HOME_DEG;
        cmdEl_ = EL_HOME_DEG;
        afterHoming();
      } else if ((in.ms - homeStartMs_) > (uint32_t)(HOMING_TIMEOUT_S * 1000.0)) {
        enterFault("HOMING_TIMEOUT");
      }
      break;
    }

    case State::IDLE:
      setTargets(cmdAz_, cmdEl_, AZ_MAX_SPEED_DPS, AZ_ACCEL_DPS2, EL_MAX_SPEED_DPS, EL_ACCEL_DPS2);
      break;

    case State::STOW:
      setTargets(STOW_AZ_DEG, STOW_EL_DEG, AZ_MAX_SPEED_DPS, AZ_ACCEL_DPS2, EL_MAX_SPEED_DPS,
                 EL_ACCEL_DPS2);
      break;

    case State::MANUAL: {
      const double v = 1.0 + trk::clamp(in.potFrac, 0.0, 1.0) * (MANUAL_MAX_SPEED_DPS - 1.0);
      if (in.encoderDelta) {
        if (manAxisEl_) manEl_ = trk::clamp(manEl_ + 0.5 * in.encoderDelta, EL_MIN_DEG, EL_MAX_DEG);
        else manAz_ = trk::clamp(manAz_ + 0.5 * in.encoderDelta, AZ_MIN_DEG, AZ_MAX_DEG);
      }
      setTargets(manAz_, manEl_, v, AZ_ACCEL_DPS2, v, EL_ACCEL_DPS2);
      break;
    }

    case State::DEMO: {
      if (!planValid_) {
        endDemo();
        mode_ = Mode::AUTO;
        enterWaitAos();
        break;
      }
      setTargets(planStartAz_, planStartEl_, AZ_MAX_SPEED_DPS, AZ_ACCEL_DPS2, EL_MAX_SPEED_DPS,
                 EL_ACCEL_DPS2);
      if (fabs(antAz_ - planStartAz_) < 0.5 && fabs(antEl_ - planStartEl_) < 0.5) {
        anchorMs_ = in.ms;
        setState(State::WAIT_AOS);
      }
      break;
    }

    case State::WAIT_AOS: {
      const bool stale = !pass_.valid || (pass_.sets && tSim_ > pass_.los + 1.0);
      if (stale && (!passTried_ || (ms_ - passTryMs_) > 10000)) computePass(tSim_);
      if (lookValid_ && look_.el > MASK_EL_DEG) {
        enterTracking();
        pointingTick();
        break;
      }
      if (pass_.valid && planValid_ && pass_.aos - tSim_ <= PREPOSITION_LEAD_S) {
        setTargets(planStartAz_, planStartEl_, AZ_MAX_SPEED_DPS, AZ_ACCEL_DPS2, EL_MAX_SPEED_DPS,
                   EL_ACCEL_DPS2);
      } else {
        setTargets(STOW_AZ_DEG, STOW_EL_DEG, AZ_MAX_SPEED_DPS, AZ_ACCEL_DPS2, EL_MAX_SPEED_DPS,
                   EL_ACCEL_DPS2);
      }
      break;
    }

    case State::ACQUIRE:
    case State::TRACK: {
      if (!lookValid_ || look_.el <= MASK_EL_DEG) {
        char t[32];
        proto::isoUtc(tSim_, t, sizeof(t));
        const double rms = errN_ ? sqrt(errSum2_ / errN_) : 0.0;
        emitf("{\"ev\":\"LOS\",\"sat\":%ld,\"t_utc\":\"%s\",\"max_err\":%.3f,\"rms_err\":%.3f,"
              "\"n\":%ld,\"comp\":%d,\"warp\":%d}",
              satId_, t, errMax_, rms, errN_, comp_ ? 1 : 0, demo_ ? warp_ : 1);
        pendingBeep_ = BEEP_LOS;
        if (demo_) {
          endDemo();
          mode_ = Mode::AUTO;
        }
        pass_.valid = false;
        passTried_ = false;
        enterWaitAos();
        break;
      }
      pointingTick();
      if (state_ == State::ACQUIRE && err_ < ACQUIRE_ERR_DEG) setState(State::TRACK);
      if (state_ == State::TRACK) {
        errSum2_ += err_ * err_;
        errN_++;
        if (err_ > errMax_) errMax_ = err_;
      }
      break;
    }

    case State::ESTOP:
      out_.driversEnabled = false;
      out_.relayOn = false;
      if (!in.estop && !estopReleasedSaid_) {
        emit("{\"ev\":\"INFO\",\"msg\":\"ESTOP_RELEASED_PRESS_HOME\"}");
        estopReleasedSaid_ = true;
      }
      break;

    case State::FAULT:
      out_.driversEnabled = false;
      out_.relayOn = false;
      break;
  }

  if (state_ != State::BOOT && state_ != State::ESTOP && state_ != State::FAULT) {
    out_.driversEnabled = true;
    out_.relayOn = true;
  }
  if (pendingTle_) {
    out_.tleRequest = pendingTle_;
    pendingTle_ = 0;
  }
  out_.beep = pendingBeep_;
  pendingBeep_ = BEEP_NONE;
  leds();
  if (tick_ % (CONTROL_HZ / TELEMETRY_HZ) == 0) telemetry();
  tick_++;
  return out_;
}

void Controller::leds() {
  const bool blink = ((ms_ / 250) & 1) != 0;
  uint8_t l = 0;
  switch (state_) {
    case State::TRACK: l = LED_GREEN; break;
    case State::ACQUIRE: l = blink ? LED_GREEN : 0; break;
    case State::HOMING: l = blink ? LED_YELLOW : 0; break;
    case State::ESTOP: l = LED_RED; break;
    case State::FAULT: l = blink ? LED_RED : 0; break;
    default: l = LED_YELLOW; break;
  }
  out_.leds = l;
}

void Controller::telemetry() {
  char t[32], aos[40] = "null", los[40] = "null", maxEl[16] = "null";
  proto::isoUtc(tSim_, t, sizeof(t));
  if (pass_.valid) {
    char tmp[32];
    proto::isoUtc(pass_.aos, tmp, sizeof(tmp));
    snprintf(aos, sizeof(aos), "\"%s\"", tmp);
    if (pass_.sets) {
      proto::isoUtc(pass_.los, tmp, sizeof(tmp));
      snprintf(los, sizeof(los), "\"%s\"", tmp);
    }
    snprintf(maxEl, sizeof(maxEl), "%.1f", pass_.maxEl);
  }
  const double sAz = lookValid_ ? look_.az : 0.0;
  const double sEl = lookValid_ ? look_.el : 0.0;
  const double rng = lookValid_ ? look_.rangeKm : 0.0;
  emitf("{\"t_utc\":\"%s\",\"sat\":%ld,\"sat_az\":%.2f,\"sat_el\":%.2f,\"range_km\":%.1f,"
        "\"cmd_az\":%.2f,\"cmd_el\":%.2f,\"ant_az\":%.2f,\"ant_el\":%.2f,\"roll\":%.2f,"
        "\"pitch\":%.2f,\"yaw\":%.2f,\"err_deg\":%.3f,\"mode\":\"%s\",\"next_aos\":%s,"
        "\"next_los\":%s,\"max_el\":%s,\"warp\":%d,\"comp\":%d,\"kh\":%d,\"src\":\"%s\","
        "\"tle_age\":%.1f,\"tle_fb\":%d,\"axis\":\"%s\"}",
        t, satId_, sAz, sEl, rng, cmdAz_, cmdEl_, antAz_, antEl_, roll_, pitch_, yaw_, err_,
        stateName(state_), aos, los, maxEl, demo_ ? warp_ : 1, comp_ ? 1 : 0, keyhole_ ? 1 : 0,
        src_, tleAgeDays(), tleFallback() ? 1 : 0, manAxisEl_ ? "EL" : "AZ");
}

}  // namespace ctl
