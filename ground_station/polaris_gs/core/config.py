"""System constants. Mirror of firmware/include/config.h (checked by tests)."""

FW_VERSION = "1.0.0"

# Ground station: Politehnica Bucuresti
STATION_LAT_DEG = 44.4386
STATION_LON_DEG = 26.0494
STATION_ALT_M = 80.0

# Tracking
MASK_EL_DEG = 5.0              # track only above this elevation
ACQUIRE_ERR_DEG = 1.0          # ACQUIRE -> TRACK when error is below this
KEYHOLE_ERR_DEG = 0.5          # rate-limit error reported as keyhole above this
KEYHOLE_EL_DEG = 70.0          # above this a rate limit hit is a keyhole
PREPOSITION_LEAD_S = 120.0     # move to the rise azimuth this long before AOS
DEMO_LEAD_S = 60.0             # DEMO jumps the clock to AOS minus this
DEMO_MIN_MAX_EL_DEG = 20.0     # DEMO skips low passes
PASS_SAMPLE_S = 2.0            # pass profile sampling period
PASS_MAX_SAMPLES = 900         # 30 min of profile
PASS_SEARCH_H = 24.0
PASS_SCAN_PER_TICK = 12      # coarse pass search samples per control tick (keeps the loop short)           # look-ahead for the next pass
KEYHOLE_PLAN_MARGIN = 0.8      # plan with 80 % of the max axis speed

# Mechanics: 200 steps/rev x 16 microsteps x 5:1 gear
MOTOR_STEPS_PER_REV = 200
MICROSTEPS = 16
GEAR_RATIO = 5.0
STEPS_PER_DEG = MOTOR_STEPS_PER_REV * MICROSTEPS * GEAR_RATIO / 360.0
DEG_PER_STEP = 1.0 / STEPS_PER_DEG

# Axis limits (software). Azimuth range is set by the cable wrap.
AZ_MIN_DEG = -270.0
AZ_MAX_DEG = 270.0
EL_MIN_DEG = -10.0
EL_MAX_DEG = 90.0

# Motion profiles
AZ_MAX_SPEED_DPS = 40.0
AZ_ACCEL_DPS2 = 120.0
EL_MAX_SPEED_DPS = 30.0
EL_ACCEL_DPS2 = 120.0
HOMING_SPEED_DPS = 15.0
MANUAL_MAX_SPEED_DPS = 20.0

# Homing: limit switches sit just past the soft limits
AZ_HOME_DEG = -275.0
EL_HOME_DEG = -12.0
HOMING_TIMEOUT_S = 45.0
# SIMULATION build: switch "reached" after this many steps
SIM_HOME_AZ_STEPS = 2000
SIM_HOME_EL_STEPS = 889

# Parking
STOW_AZ_DEG = 0.0
STOW_EL_DEG = 90.0

# Vehicle
VEHICLE_YAW_DEFAULT_DEG = 90.0  # ROS REP-103: yaw 90 = facing north
COMP_FILTER_ALPHA = 0.98
VEH_TIMEOUT_S = 1.0

# Rates
TELEMETRY_HZ = 10
SAT_HZ = 10
CONTROL_HZ = 50

DEMO_WARPS = (10, 30, 60)
DEFAULT_DEMO_WARP = 30

SATELLITES = {
    25544: "ISS",
    33591: "NOAA 19",
    28654: "NOAA 18",
    43700: "QO-100",
}
DEFAULT_SAT = 25544
