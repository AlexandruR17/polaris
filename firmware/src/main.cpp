// POLARIS SAT-1: vehicle mounted satellite tracking antenna.
//
// Core 1 (Arduino loop): step generation only (AccelStepper), never blocks.
// Core 0, control task (50 Hz): inputs, state machine, outputs, displays,
//   serial protocol. SGP4 runs inside the controller at 10 Hz.
// Core 0, network task: TLE downloads on request, so HTTPS never blocks
//   the control loop.
#include <AccelStepper.h>
#include <Adafruit_MPU6050.h>
#include <Arduino.h>
#include <Wire.h>
#include <esp_system.h>

#include "hmi.h"
#include "net.h"
#include "pc_config.h"
#include "pc_controller.h"
#include "pc_tle_fallback.h"
#include "pins.h"

#ifndef POLARIS_SIMULATION
#define POLARIS_SIMULATION 1
#endif
#ifndef POLARIS_QEMU
#define POLARIS_QEMU 0  // 1 only for the QEMU smoke test: no WiFi radio, no ADC
#endif

static AccelStepper azStepper(AccelStepper::DRIVER, PIN_AZ_STEP, PIN_AZ_DIR);
static AccelStepper elStepper(AccelStepper::DRIVER, PIN_EL_STEP, PIN_EL_DIR);
static Adafruit_MPU6050 mpu;
static bool mpuOk = false;
static ctl::Controller controller;

// Motion command handed from the control task to the stepper loop
struct MotionCmd {
  long azTarget = 0, elTarget = 0;
  bool azSetPos = false, elSetPos = false;
  double azV = 0, azA = 0, elV = 0, elA = 0;
  bool enabled = false;
  bool stopNow = false;
  uint32_t seq = 0;
};
static portMUX_TYPE motionMux = portMUX_INITIALIZER_UNLOCKED;
static MotionCmd sharedCmd;
static volatile long azPos = 0, elPos = 0;

struct TleResult {
  long catnr;
  bool ok;
  net::Tle tle;
};
static QueueHandle_t tleRequests;
static QueueHandle_t tleResults;

static void emitSerial(void*, const char* line) { Serial.println(line); }

static void info(const char* msg) {
  Serial.print("{\"ev\":\"INFO\",\"msg\":\"");
  Serial.print(msg);
  Serial.println("\"}");
}

static void publishMotion(const ctl::Outputs& o) {
  portENTER_CRITICAL(&motionMux);
  sharedCmd.azTarget = o.az.target;
  sharedCmd.elTarget = o.el.target;
  // one-shot flags stay set until the stepper loop consumes them
  sharedCmd.azSetPos |= o.az.setPos;
  sharedCmd.elSetPos |= o.el.setPos;
  sharedCmd.stopNow |= o.stopNow;
  sharedCmd.azV = o.az.maxSpeedDps;
  sharedCmd.azA = o.az.accelDps2;
  sharedCmd.elV = o.el.maxSpeedDps;
  sharedCmd.elA = o.el.accelDps2;
  sharedCmd.enabled = o.driversEnabled;
  sharedCmd.seq++;
  portEXIT_CRITICAL(&motionMux);
}

static void readImu(ctl::Inputs& in) {
  in.imuOk = false;
  if (!mpuOk) return;
  sensors_event_t a, g, t;
  if (!mpu.getEvent(&a, &g, &t)) return;
  // sensor x forward, y left, z up (same as the vehicle FLU frame)
  in.ax = a.acceleration.x / SENSORS_GRAVITY_STANDARD;
  in.ay = a.acceleration.y / SENSORS_GRAVITY_STANDARD;
  in.az = a.acceleration.z / SENSORS_GRAVITY_STANDARD;
  in.gx = g.gyro.x * geo::R2D;
  in.gy = g.gyro.y * geo::R2D;
  in.imuOk = true;
}

static void controlTask(void*) {
  ctl::Inputs in;
  in.ms = millis();
  in.tReal = net::nowUnix();
  in.azSteps = azPos;
  in.elSteps = elPos;
  controller.bootDone(in);

  TickType_t last = xTaskGetTickCount();
  const TickType_t period = pdMS_TO_TICKS(1000 / cfg::CONTROL_HZ);
  char rx[100];
  size_t rxn = 0;
  uint32_t tick = 0;
  for (;;) {
    vTaskDelayUntil(&last, period);
    in.ms = millis();
    in.tReal = net::nowUnix();
    hmi::readInputs(in);
    readImu(in);
    in.azSteps = azPos;
    in.elSteps = elPos;

    while (Serial.available()) {
      const char c = (char)Serial.read();
      if (c == '\n' || c == '\r') {
        if (rxn) {
          rx[rxn] = 0;
          controller.command(rx);
          rxn = 0;
        }
      } else if (rxn < sizeof(rx) - 1) {
        rx[rxn++] = c;
      }
    }
    TleResult r;
    while (xQueueReceive(tleResults, &r, 0) == pdTRUE) {
      if (r.ok) controller.loadTle(r.catnr, r.tle.name, r.tle.l1, r.tle.l2, false, in.tReal, true);
      else controller.tleDownloadFailed(r.catnr, in.tReal);
    }

    const ctl::Outputs& o = controller.update(in);
    publishMotion(o);
    if (o.tleRequest) xQueueSend(tleRequests, &o.tleRequest, 0);
    hmi::applyOutputs(o);
    hmi::serviceBuzzer(in.ms);
    if (tick % 10 == 3) hmi::drawOled(controller);           // 5 Hz
    if (tick % 25 == 11) hmi::drawLcd(controller, in.tReal);  // 2 Hz
    tick++;
    // a long tick (pass search, slow I2C) must still let the idle task run,
    // otherwise the task watchdog resets the board
    if ((TickType_t)(xTaskGetTickCount() - last) >= period) vTaskDelay(1);
  }
}

static void networkTask(void*) {
  long id;
  for (;;) {
    if (xQueueReceive(tleRequests, &id, portMAX_DELAY) != pdTRUE) continue;
    TleResult r{};
    r.catnr = id;
    r.ok = net::downloadTle(id, r.tle, 8000);
    xQueueSend(tleResults, &r, portMAX_DELAY);
  }
}

static const char* resetReason() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON: return "POWERON";
    case ESP_RST_SW: return "SOFTWARE";
    case ESP_RST_PANIC: return "PANIC";
    case ESP_RST_INT_WDT: return "INT_WDT";
    case ESP_RST_TASK_WDT: return "TASK_WDT";
    case ESP_RST_WDT: return "WDT";
    case ESP_RST_BROWNOUT: return "BROWNOUT";
    case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
    default: return "OTHER";
  }
}

static void setupStepper(AccelStepper& s, int enPin, double vDps, double aDps2) {
  s.setEnablePin(enPin);
  s.setPinsInverted(false, false, true);  // A4988 ENABLE is active low
  s.disableOutputs();
  s.setMinPulseWidth(3);
  s.setMaxSpeed(vDps * cfg::STEPS_PER_DEG);
  s.setAcceleration(aDps2 * cfg::STEPS_PER_DEG);
}

void setup() {
  Serial.setTxBufferSize(4096);
  // commands keep arriving while setup() is busy with WiFi and TLE: buffer them
  Serial.setRxBufferSize(2048);
  Serial.begin(115200);
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);
  setupStepper(azStepper, PIN_AZ_EN, cfg::AZ_MAX_SPEED_DPS, cfg::AZ_ACCEL_DPS2);
  setupStepper(elStepper, PIN_EL_EN, cfg::EL_MAX_SPEED_DPS, cfg::EL_ACCEL_DPS2);
  hmi::begin();

  controller.begin(POLARIS_SIMULATION != 0, emitSerial, nullptr);
  for (int i = 0; i < FALLBACK_TLE_COUNT; i++)
    controller.loadTle(FALLBACK_TLES[i].catnr, FALLBACK_TLES[i].name, FALLBACK_TLES[i].l1,
                       FALLBACK_TLES[i].l2, true, 0, false);

  mpuOk = mpu.begin(0x68, &Wire);
  if (mpuOk) {
    mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
    mpu.setGyroRange(MPU6050_RANGE_250_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  }
  info(mpuOk ? "MPU_OK" : "MPU_MISSING");
  Serial.printf("{\"ev\":\"INFO\",\"msg\":\"RESET\",\"reason\":\"%s\"}\n", resetReason());

  hmi::splashStatus("WiFi Wokwi-GUEST...");
  const bool wifi = POLARIS_QEMU ? false : net::connectWifi(15000);
  info(wifi ? "WIFI_OK" : "WIFI_FAIL");
  hmi::splashStatus("Sincronizare NTP...");
  const bool ntp = wifi && net::syncTime(10000);
  if (!wifi) net::syncTime(0);
  info(ntp ? "NTP_OK" : "NTP_FAIL_BUILD_TIME");
  hmi::splashStatus("Descărcare TLE...");
  net::Tle tle;
  if (wifi && net::downloadTle(cfg::DEFAULT_SAT, tle, 8000)) {
    controller.loadTle(cfg::DEFAULT_SAT, tle.name, tle.l1, tle.l2, false, net::nowUnix(), true);
    hmi::splashStatus("TLE descărcat");
  } else {
    controller.tleDownloadFailed(cfg::DEFAULT_SAT, net::nowUnix());
    hmi::splashStatus("TLE vechi (rezervă)");
  }

  tleRequests = xQueueCreate(4, sizeof(long));
  tleResults = xQueueCreate(4, sizeof(TleResult));
  xTaskCreatePinnedToCore(networkTask, "net", 12288, nullptr, 1, nullptr, 0);
  xTaskCreatePinnedToCore(controlTask, "control", 16384, nullptr, 2, nullptr, 0);
}

// Stepper loop on core 1
void loop() {
  static uint32_t seen = 0;
  static bool enabled = false;
  static double azV = -1, azA = -1, elV = -1, elA = -1;

  // E-STOP acts here directly, before the control task even sees it
  if (enabled && hmi::estopPressed()) {
    azStepper.disableOutputs();
    elStepper.disableOutputs();
    azStepper.setCurrentPosition(azStepper.currentPosition());
    elStepper.setCurrentPosition(elStepper.currentPosition());
    digitalWrite(PIN_RELAY, LOW);
    enabled = false;
  }

  if (sharedCmd.seq != seen) {
    MotionCmd c;
    portENTER_CRITICAL(&motionMux);
    c = sharedCmd;
    sharedCmd.azSetPos = sharedCmd.elSetPos = sharedCmd.stopNow = false;
    portEXIT_CRITICAL(&motionMux);
    seen = c.seq;
    if (c.stopNow) {
      azStepper.setCurrentPosition(azStepper.currentPosition());
      elStepper.setCurrentPosition(elStepper.currentPosition());
    }
    if (c.enabled != enabled && !(c.enabled && hmi::estopPressed())) {
      enabled = c.enabled;
      if (enabled) {
        azStepper.enableOutputs();
        elStepper.enableOutputs();
      } else {
        azStepper.disableOutputs();
        elStepper.disableOutputs();
      }
    }
    if (c.azV > 0 && c.azV != azV) azStepper.setMaxSpeed((azV = c.azV) * cfg::STEPS_PER_DEG);
    if (c.azA > 0 && c.azA != azA) azStepper.setAcceleration((azA = c.azA) * cfg::STEPS_PER_DEG);
    if (c.elV > 0 && c.elV != elV) elStepper.setMaxSpeed((elV = c.elV) * cfg::STEPS_PER_DEG);
    if (c.elA > 0 && c.elA != elA) elStepper.setAcceleration((elA = c.elA) * cfg::STEPS_PER_DEG);
    if (c.azSetPos) azStepper.setCurrentPosition(c.azTarget);
    else azStepper.moveTo(c.azTarget);
    if (c.elSetPos) elStepper.setCurrentPosition(c.elTarget);
    else elStepper.moveTo(c.elTarget);
  }

  if (enabled) {
    azStepper.run();
    elStepper.run();
  }
  azPos = azStepper.currentPosition();
  elPos = elStepper.currentPosition();
}
