// POLARIS SAT-1 state machine. Hardware independent: the firmware feeds
// Inputs at CONTROL_HZ and applies the Outputs. The same class runs on the
// PC in the native test harness. Mirror: polaris_gs/sim/controller.py.
#pragma once

#include <stdint.h>

#include "pc_config.h"
#include "pc_filter.h"
#include "pc_orbit.h"
#include "pc_protocol.h"

namespace ctl {

enum class State : uint8_t { BOOT, HOMING, IDLE, WAIT_AOS, ACQUIRE, TRACK, STOW, MANUAL, DEMO, ESTOP, FAULT };
enum class Mode : uint8_t { AUTO, MANUAL, DEMO, IDLE, STOW };

const char* stateName(State s);
const char* modeName(Mode m);

enum Beep : uint8_t { BEEP_NONE = 0, BEEP_AOS = 1, BEEP_LOS = 2, BEEP_ERROR = 3, BEEP_OK = 4 };
enum Led : uint8_t { LED_GREEN = 1, LED_YELLOW = 2, LED_RED = 4 };

struct Inputs {
  uint32_t ms = 0;        // monotonic milliseconds
  double tReal = 0;       // UTC unix seconds
  bool estop = false;     // E-STOP pressed
  bool limAz = false;     // limit switch active
  bool limEl = false;
  long azSteps = 0;       // current axis positions
  long elSteps = 0;
  bool imuOk = false;     // MPU6050 sample valid
  double ax = 0, ay = 0, az = 1;  // g
  double gx = 0, gy = 0;          // deg/s
  int encoderDelta = 0;   // detents since last update (+ = clockwise)
  bool encoderPress = false;  // press events since last update
  bool btnMode = false;
  bool btnHome = false;
  bool btnStow = false;
  double potFrac = 0.5;   // 0..1
};

struct AxisCmd {
  long target = 0;
  bool setPos = false;    // one-shot: set the current position to target
  double maxSpeedDps = 0;
  double accelDps2 = 0;
};

struct Outputs {
  bool driversEnabled = false;
  bool relayOn = false;
  bool stopNow = false;   // one-shot hard stop
  AxisCmd az, el;
  uint8_t leds = 0;
  uint8_t beep = BEEP_NONE;  // one-shot
  long tleRequest = 0;       // one-shot: firmware should download this TLE
};

typedef void (*EmitFn)(void* ctx, const char* line);

struct SatSlot {
  long catnr;
  char name[25];
  char l1[72];
  char l2[72];
  bool loaded;
  bool fallback;
  bool tried;
};

constexpr int NUM_SATS = 4;
extern const long SAT_IDS[NUM_SATS];

class Controller {
 public:
  Controller();
  void begin(bool simLimits, EmitFn emit, void* ctx);
  // Load a TLE. announce: emit TLE_OK (downloaded) or TLE_FALLBACK (stored).
  bool loadTle(long catnr, const char* name, const char* l1, const char* l2, bool fallback,
               double tNow, bool announce);
  // Download failed: keep the stored TLE and report its age
  void tleDownloadFailed(long catnr, double tNow);
  void bootDone(const Inputs& in);
  void command(const char* line);
  const Outputs& update(const Inputs& in);

  // read access for displays
  State state() const { return state_; }
  Mode mode() const { return mode_; }
  double tSim() const { return tSim_; }
  long satId() const { return satId_; }
  const char* satName() const { return sat_.name(); }
  bool satReady() const { return sat_.ready(); }
  double satAz() const { return look_.az; }
  double satEl() const { return look_.el; }
  double rangeKm() const { return look_.rangeKm; }
  double cmdAz() const { return cmdAz_; }
  double cmdEl() const { return cmdEl_; }
  double antAz() const { return antAz_; }
  double antEl() const { return antEl_; }
  double errDeg() const { return err_; }
  double roll() const { return roll_; }
  double pitch() const { return pitch_; }
  double yaw() const { return yaw_; }
  const orbit::Pass& pass() const { return pass_; }
  bool tleFallback() const;
  double tleAgeDays() const { return sat_.ready() ? sat_.ageDays(tSim_) : 0; }
  int warp() const { return demo_ ? warp_ : 1; }
  bool demo() const { return demo_; }
  bool comp() const { return comp_; }
  bool keyhole() const { return keyhole_; }
  bool manualAxisEl() const { return manAxisEl_; }
  const char* faultCode() const { return fault_; }
  const char* attSource() const { return src_; }

 private:
  void emit(const char* line);
  void emitf(const char* fmt, ...);
  void setState(State s);
  void applyMode();
  void startHoming();
  void afterHoming();
  void enterWaitAos();
  void enterTracking();
  void enterDemo();
  void endDemo();
  void enterEstop();
  void enterFault(const char* code);
  void ack();
  void selectSat(long id);
  void computePass(double t);
  void buildPlan(double tFrom, double refAz);
  double planLeadAt(double t) const;
  double planAzAt(double t) const;
  void refreshLook(bool reset);
  geo::Vec3 satEnuAt(double t) const;
  void pointingTick();
  void updateAttitude(const Inputs& in);
  void setTargets(double azDeg, double elDeg, double vAz, double aAz, double vEl, double aEl);
  void telemetry();
  void leds();
  int slotIndex(long id) const;

  bool simLimits_ = true;
  EmitFn emitFn_ = nullptr;
  void* emitCtx_ = nullptr;

  SatSlot slots_[NUM_SATS];
  orbit::Satellite sat_;
  long satId_;

  State state_ = State::BOOT;
  Mode mode_ = Mode::AUTO;
  Outputs out_;
  uint32_t tick_ = 0;
  uint32_t ms_ = 0;
  Inputs in_;

  // clock
  double tSim_ = 0;
  bool demo_ = false;
  int warp_ = 1;
  int demoWarp_ = cfg::DEFAULT_DEMO_WARP;
  uint32_t anchorMs_ = 0;
  double anchorSim_ = 0;

  // attitude
  ComplementaryFilter filter_;
  double roll_ = 0, pitch_ = 0, yaw_ = cfg::VEHICLE_YAW_DEFAULT_DEG;
  bool vehActive_ = false;
  double vehRoll_ = 0, vehPitch_ = 0, vehYaw_ = 0;
  uint32_t vehMs_ = 0;
  uint32_t imuMs_ = 0;
  bool imuSeen_ = false;
  const char* src_ = "NONE";
  bool comp_ = true;

  // satellite look (10 Hz) with linear extrapolation in between
  orbit::Look look_{};
  bool lookValid_ = false;
  geo::Vec3 prevEnu_{0, 0, 1};
  double prevT_ = 0;
  bool prevValid_ = false;
  double lookT_ = 0;

  // pass and plan
  orbit::Pass pass_{};
  uint32_t passTryMs_ = 0;
  bool passTried_ = false;
  bool planValid_ = false;
  int planN_ = 0;
  double planT0_ = 0, planDt_ = 1;
  double planStartAz_ = 0, planStartEl_ = 0;
  static float planLead_[cfg::PASS_MAX_SAMPLES];
  static float planAz_[cfg::PASS_MAX_SAMPLES];
  static double work0_[cfg::PASS_MAX_SAMPLES];
  static double work1_[cfg::PASS_MAX_SAMPLES];
  static double work2_[cfg::PASS_MAX_SAMPLES];

  // pointing
  double antAz_ = 0, antEl_ = 0;
  double cmdAz_ = 0, cmdEl_ = 0;
  bool haveRaw_ = false;
  double rawAz_ = 0;
  uint32_t rawMs_ = 0;
  double reqRate_ = 0;
  double err_ = 0;
  bool keyhole_ = false;
  bool khZenith_ = false;
  uint32_t khMs_ = 0;
  double errSum2_ = 0, errMax_ = 0;
  long errN_ = 0;

  // homing
  uint32_t homeStartMs_ = 0;
  bool azHomed_ = false, elHomed_ = false;
  long azStart_ = 0, elStart_ = 0;
  bool limArmedAz_ = true, limArmedEl_ = true;

  // manual
  bool manAxisEl_ = false;
  double manAz_ = 0, manEl_ = 0;

  // safety
  bool estopReleasedSaid_ = false;
  char fault_[24] = {0};
  long pendingTle_ = 0;
  uint8_t pendingBeep_ = BEEP_NONE;
};

}  // namespace ctl
