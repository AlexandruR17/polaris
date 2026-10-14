"""Frames and pointing geometry.

World frame: local ENU (x east, y north, z up).
Vehicle frame: FLU (x forward, y left, z up), ROS REP-103.
Attitude: R = Rz(yaw) * Ry(pitch) * Rx(roll), body = R^T * enu.
yaw = 0 means the vehicle faces east, yaw = 90 faces north.
Pedestal azimuth: 0 = vehicle forward, positive clockwise seen from above.
"""
import math

import numpy as np

D2R = math.pi / 180.0
R2D = 180.0 / math.pi


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def attitude_matrix(roll_deg, pitch_deg, yaw_deg):
    """R = Rz(yaw) Ry(pitch) Rx(roll). Maps body vectors into ENU."""
    return rot_z(yaw_deg * D2R) @ rot_y(pitch_deg * D2R) @ rot_x(roll_deg * D2R)


def azel_to_enu(az_deg, el_deg):
    """Unit vector in ENU. Azimuth from north, clockwise."""
    az, el = az_deg * D2R, el_deg * D2R
    return np.array([math.cos(el) * math.sin(az), math.cos(el) * math.cos(az), math.sin(el)])


def enu_to_azel(v):
    e, n, u = v
    az = math.atan2(e, n) * R2D
    if az < 0:
        az += 360.0
    el = math.atan2(u, math.hypot(e, n)) * R2D
    return az, el


def enu_to_body(v_enu, roll_deg, pitch_deg, yaw_deg):
    return attitude_matrix(roll_deg, pitch_deg, yaw_deg).T @ np.asarray(v_enu, dtype=float)


def body_to_enu(v_body, roll_deg, pitch_deg, yaw_deg):
    return attitude_matrix(roll_deg, pitch_deg, yaw_deg) @ np.asarray(v_body, dtype=float)


def body_to_pedestal(v_body):
    """Pedestal az in [-180, 180), el in [-90, 90]."""
    x, y, z = v_body
    az = math.atan2(-y, x) * R2D
    el = math.atan2(z, math.hypot(x, y)) * R2D
    return wrap180(az), el


def pedestal_to_body(az_deg, el_deg):
    az, el = az_deg * D2R, el_deg * D2R
    return np.array([math.cos(el) * math.cos(az), -math.cos(el) * math.sin(az), math.sin(el)])


def pointing_command(sat_az, sat_el, roll, pitch, yaw, compensate=True):
    """Pedestal az/el that points at (sat_az, sat_el) given vehicle attitude.

    Without compensation the vehicle is assumed level (only yaw is used).
    """
    v = azel_to_enu(sat_az, sat_el)
    if compensate:
        b = enu_to_body(v, roll, pitch, yaw)
    else:
        b = enu_to_body(v, 0.0, 0.0, yaw)
    return body_to_pedestal(b)


def boresight_enu(ped_az, ped_el, roll, pitch, yaw):
    return body_to_enu(pedestal_to_body(ped_az, ped_el), roll, pitch, yaw)


def angle_between(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    c = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    # atan2 form keeps precision for small angles
    s = float(np.linalg.norm(np.cross(a, b)) / (np.linalg.norm(a) * np.linalg.norm(b)))
    return math.atan2(s, c) * R2D


def pointing_error(ped_az, ped_el, roll, pitch, yaw, sat_az, sat_el):
    """True angle between antenna boresight and satellite direction."""
    return angle_between(boresight_enu(ped_az, ped_el, roll, pitch, yaw), azel_to_enu(sat_az, sat_el))


def wrap180(a):
    a = math.fmod(a + 180.0, 360.0)
    if a < 0:
        a += 360.0
    return a - 180.0


def accel_to_roll_pitch(ax, ay, az):
    """Gravity reaction in FLU body: a = (-sin p, cos p sin r, cos p cos r)."""
    roll = math.atan2(ay, az) * R2D
    pitch = math.atan2(-ax, math.hypot(ay, az)) * R2D
    return roll, pitch


def gravity_in_body(roll_deg, pitch_deg):
    r, p = roll_deg * D2R, pitch_deg * D2R
    return (-math.sin(p), math.cos(p) * math.sin(r), math.cos(p) * math.cos(r))
