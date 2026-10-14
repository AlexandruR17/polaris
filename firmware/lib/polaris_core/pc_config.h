// System constants. Mirror of ground_station/polaris_gs/core/config.py
// (tests/test_firmware_parity.py checks that both files agree).
#pragma once

#define FW_VERSION "1.0.0"

namespace cfg {

// Ground station: Politehnica Bucuresti
constexpr double STATION_LAT_DEG = 44.4386;
constexpr double STATION_LON_DEG = 26.0494;
constexpr double STATION_ALT_M = 80.0;

// Tracking
constexpr double MASK_EL_DEG = 5.0;
constexpr double ACQUIRE_ERR_DEG = 1.0;
constexpr double KEYHOLE_ERR_DEG = 0.5;
constexpr double KEYHOLE_EL_DEG = 70.0;  // above this a rate limit hit is a keyhole
constexpr double PREPOSITION_LEAD_S = 120.0;
constexpr double DEMO_LEAD_S = 60.0;
constexpr double DEMO_MIN_MAX_EL_DEG = 20.0;  // DEMO skips low passes
constexpr double PASS_SAMPLE_S = 2.0;
constexpr int PASS_MAX_SAMPLES = 900;
constexpr double PASS_SEARCH_H = 24.0;
constexpr double KEYHOLE_PLAN_MARGIN = 0.8;

// Mechanics: 200 steps/rev x 16 microsteps x 5:1 gear
constexpr int MOTOR_STEPS_PER_REV = 200;
constexpr int MICROSTEPS = 16;
constexpr double GEAR_RATIO = 5.0;
constexpr double STEPS_PER_DEG = MOTOR_STEPS_PER_REV * MICROSTEPS * GEAR_RATIO / 360.0;
constexpr double DEG_PER_STEP = 1.0 / STEPS_PER_DEG;

// Axis limits (software). Azimuth range is set by the cable wrap.
constexpr double AZ_MIN_DEG = -270.0;
constexpr double AZ_MAX_DEG = 270.0;
constexpr double EL_MIN_DEG = -10.0;
constexpr double EL_MAX_DEG = 90.0;

// Motion profiles
constexpr double AZ_MAX_SPEED_DPS = 40.0;
constexpr double AZ_ACCEL_DPS2 = 120.0;
constexpr double EL_MAX_SPEED_DPS = 30.0;
constexpr double EL_ACCEL_DPS2 = 120.0;
constexpr double HOMING_SPEED_DPS = 15.0;
constexpr double MANUAL_MAX_SPEED_DPS = 20.0;

// Homing: limit switches sit just past the soft limits
constexpr double AZ_HOME_DEG = -275.0;
constexpr double EL_HOME_DEG = -12.0;
constexpr double HOMING_TIMEOUT_S = 45.0;
// SIMULATION build: switch "reached" after this many steps
constexpr long SIM_HOME_AZ_STEPS = 2000;
constexpr long SIM_HOME_EL_STEPS = 889;

// Parking
constexpr double STOW_AZ_DEG = 0.0;
constexpr double STOW_EL_DEG = 90.0;

// Vehicle
constexpr double VEHICLE_YAW_DEFAULT_DEG = 90.0;  // ROS REP-103: yaw 90 = facing north
constexpr double COMP_FILTER_ALPHA = 0.98;
constexpr double VEH_TIMEOUT_S = 1.0;

// Rates
constexpr int TELEMETRY_HZ = 10;
constexpr int SAT_HZ = 10;
constexpr int CONTROL_HZ = 50;

constexpr int DEFAULT_SAT = 25544;
constexpr int DEFAULT_DEMO_WARP = 30;

}  // namespace cfg
