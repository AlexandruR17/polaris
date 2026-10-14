"""Fallback TLEs, identical to firmware/include/tle_fallback.h.

Source: gpredict repository, data/satdata/satellites.dat
(ISS and ES'HAIL 2 from commit c2db462, 16 Aug 2026;
NOAA 19 and NOAA 18 from commit 4a6a0c3, 22 Mar 2026).
Regenerate with tools/update_tle.py when you have access to CelesTrak.
"""

FALLBACK_TLE = {
    25544: ("ISS (ZARYA)",
            "1 25544U 98067A   26228.18012382  .00004999  00000+0  97292-4 0  9998",
            "2 25544  51.6332   3.1747 0007602  51.3505 308.8163 15.49457398581051"),
    33591: ("NOAA 19",
            "1 33591U 09005A   26081.19398128  .00000058  00000+0  54800-4 0  9996",
            "2 33591  98.9583 151.9847 0012677 276.5899  83.3830 14.13459138882191"),
    28654: ("NOAA 18",
            "1 28654U 05018A   26081.21057231  .00000048  00000+0  48542-4 0  9995",
            "2 28654  98.8139 162.1415 0014890  41.9371 318.2939 14.13713178 74026"),
    43700: ("ES'HAIL 2 (QO-100)",
            "1 43700U 18090A   26228.21251860  .00000134  00000+0  00000+0 0  9993",
            "2 43700   0.0151 101.3489 0002570  77.9933 247.5434  1.00274022 28277"),
}

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={catnr}&FORMAT=TLE"
