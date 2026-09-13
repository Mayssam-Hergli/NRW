"""Outside air temperature, and the effective temperature the thermal model
sees once solar load and airflow are accounted for.
"""

from __future__ import annotations

import math

from simulator import config
from simulator.route import WAYPOINTS, RoutePoint


def _hour_of_day(t_min: float, departure_hour: float) -> float:
    return (departure_hour + t_min / 60.0) % 24.0


def _diurnal_fraction(hour: float) -> float:
    """-1 at the trough, +1 at the peak, smooth in between.

    The rising half (trough -> peak) and falling half (peak -> next trough)
    are different lengths, so this is two half-cosines stitched together
    rather than a single symmetric sinusoid.
    """
    peak, trough = config.DIURNAL_PEAK_HOUR, config.DIURNAL_TROUGH_HOUR
    rising_span = (peak - trough) % 24.0
    falling_span = 24.0 - rising_span
    phase = (hour - trough) % 24.0
    if phase <= rising_span:
        frac = phase / rising_span
        return -math.cos(math.pi * frac)
    frac = (phase - rising_span) / falling_span
    return math.cos(math.pi * frac)


# WAYPOINTS is already ordered north (Tunis, highest lat) to south
# (Médenine, lowest lat), matching config.WAYPOINT_NIGHT_DAY_C's order.
_LAT_CLIMATE_TABLE: list[tuple[float, float, float]] = [
    (lat, *config.WAYPOINT_NIGHT_DAY_C[name]) for name, lat, _lon in WAYPOINTS
]


def _night_day_c_at_lat(lat: float) -> tuple[float, float]:
    table = _LAT_CLIMATE_TABLE
    if lat >= table[0][0]:
        return table[0][1], table[0][2]
    if lat <= table[-1][0]:
        return table[-1][1], table[-1][2]
    for i in range(len(table) - 1):
        lat_hi, night_hi, day_hi = table[i]
        lat_lo, night_lo, day_lo = table[i + 1]
        if lat_lo <= lat <= lat_hi:
            frac = (lat_hi - lat) / (lat_hi - lat_lo)
            night = night_hi + (night_lo - night_hi) * frac
            day = day_hi + (day_lo - day_hi) * frac
            return night, day
    return table[-1][1], table[-1][2]


def ambient_c(t_min: float, point: RoutePoint, departure_hour: float) -> float:
    """Raw outside air temperature. Diurnal cycle plus the north-south /
    inland climate gradient. Does not include solar or airflow effects --
    use effective_ambient_c for driving the thermal model.
    """
    night_c, day_c = _night_day_c_at_lat(point.lat)
    mean = (day_c + night_c) / 2.0
    amplitude = (day_c - night_c) / 2.0
    hour = _hour_of_day(t_min, departure_hour)
    return mean + amplitude * _diurnal_fraction(hour)


def _solar_intensity(hour: float) -> float:
    """0..1 bell curve centered on SOLAR_PEAK_HOUR, zero outside the
    daylight half-width."""
    delta = ((hour - config.SOLAR_PEAK_HOUR + 12.0) % 24.0) - 12.0
    half_width = config.SOLAR_HALF_WIDTH_HOURS
    if abs(delta) >= half_width:
        return 0.0
    return math.cos((math.pi / 2.0) * (delta / half_width))


def effective_ambient_c(t_min: float, point: RoutePoint, departure_hour: float) -> float:
    """What the thermal model should use: raw air temperature plus solar
    load, worse when the vehicle is stationary (no condenser airflow)."""
    air = ambient_c(t_min, point, departure_hour)
    hour = _hour_of_day(t_min, departure_hour)
    intensity = _solar_intensity(hour)
    moving = point.speed_kmh > config.STATIONARY_SPEED_THRESHOLD_KMH
    solar_max = config.SOLAR_LOAD_MOVING_MAX_C if moving else config.SOLAR_LOAD_STATIONARY_MAX_C
    return air + solar_max * intensity
