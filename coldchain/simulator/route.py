"""The corridor the truck drives, and where it is at any moment.

Builds a full time/position schedule once (at Route construction) by
stepping forward in small increments, handling acceleration, deceleration,
and offload stops as a small state machine. Route.position_at then just
looks up (and interpolates) that precomputed schedule.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from simulator import config

WAYPOINTS: list[tuple[str, float, float]] = [
    ("Tunis", 36.80, 10.18),
    ("Sousse", 35.83, 10.64),
    ("Sfax", 34.74, 10.76),
    ("Gabès", 33.88, 10.10),
    ("Médenine", 33.35, 10.50),
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * earth_radius_km * math.asin(math.sqrt(a))


@dataclass
class RoutePoint:
    lat: float
    lon: float
    speed_kmh: float
    km_travelled: float
    nearest_waypoint: str


class _StopState:
    """Tracks progress through one configured offload stop."""

    def __init__(self, waypoint_index: int, duration_min: float, stop_km: float) -> None:
        self.waypoint_index = waypoint_index
        self.duration_min = duration_min
        self.stop_km = stop_km
        self.remaining_wait_min = duration_min
        self.done = False
        self.waiting = False


class Route:
    def __init__(
        self,
        waypoints: list[tuple[str, float, float]] | None = None,
        offload_stops: list[tuple[int, float]] | None = None,
    ) -> None:
        self.waypoints = waypoints if waypoints is not None else WAYPOINTS
        stops = offload_stops if offload_stops is not None else config.DEFAULT_OFFLOAD_STOPS

        self._segment_km: list[float] = []
        cumulative = [0.0]
        for i in range(len(self.waypoints) - 1):
            _, lat1, lon1 = self.waypoints[i]
            _, lat2, lon2 = self.waypoints[i + 1]
            d = haversine_km(lat1, lon1, lat2, lon2) * config.ROAD_DISTANCE_FACTOR
            self._segment_km.append(d)
            cumulative.append(cumulative[-1] + d)
        self._cumulative_km = cumulative
        self.total_km = cumulative[-1]

        self._stops = [
            _StopState(idx, duration, cumulative[idx]) for idx, duration in stops
        ]

        self._schedule: list[RoutePoint] = []
        self._schedule_t_min: list[float] = []
        self._build_schedule()

    def _latlon_at_km(self, km: float) -> tuple[float, float, str]:
        km = max(0.0, min(km, self.total_km))
        for i in range(len(self._segment_km)):
            seg_start = self._cumulative_km[i]
            seg_len = self._segment_km[i]
            seg_end = self._cumulative_km[i + 1]
            if km <= seg_end or i == len(self._segment_km) - 1:
                frac = 0.0 if seg_len == 0 else (km - seg_start) / seg_len
                frac = max(0.0, min(1.0, frac))
                name1, lat1, lon1 = self.waypoints[i]
                name2, lat2, lon2 = self.waypoints[i + 1]
                lat = lat1 + (lat2 - lat1) * frac
                lon = lon1 + (lon2 - lon1) * frac
                nearest = name1 if frac < 0.5 else name2
                return lat, lon, nearest
        # Unreachable given the clamp above, but keeps type checkers happy.
        name, lat, lon = self.waypoints[-1]
        return lat, lon, name

    def _build_schedule(self) -> None:
        rng = random.Random(config.ROUTE_RNG_SEED)
        dt_min = config.ROUTE_DT_MIN
        t_min = 0.0
        km = 0.0
        speed = 0.0
        next_stop_idx = 0

        while True:
            lat, lon, nearest = self._latlon_at_km(km)
            self._schedule.append(
                RoutePoint(
                    lat=lat, lon=lon, speed_kmh=speed, km_travelled=km, nearest_waypoint=nearest
                )
            )
            self._schedule_t_min.append(t_min)

            if km >= self.total_km:
                break

            active_stop = self._stops[next_stop_idx] if next_stop_idx < len(self._stops) else None

            if active_stop is not None and active_stop.waiting:
                speed = 0.0
                active_stop.remaining_wait_min -= dt_min
                if active_stop.remaining_wait_min <= 0:
                    active_stop.waiting = False
                    active_stop.done = True
                    next_stop_idx += 1
            elif (
                active_stop is not None
                and not active_stop.done
                and active_stop.stop_km - km <= config.STOP_LOOKAHEAD_KM
            ):
                remaining = max(0.0, active_stop.stop_km - km)
                if remaining <= 0.0 or speed <= config.STOP_SNAP_SPEED_KMH:
                    speed = 0.0
                    active_stop.waiting = True
                else:
                    speed = max(0.0, speed - config.DECEL_RATE_KMH_PER_MIN * dt_min)
            else:
                target = config.CRUISE_SPEED_KMH + rng.gauss(0.0, config.SPEED_NOISE_STD_KMH)
                target = max(0.0, target)
                if speed < target:
                    speed = min(target, speed + config.ACCEL_RATE_KMH_PER_MIN * dt_min)
                else:
                    speed = max(target, speed - config.DECEL_RATE_KMH_PER_MIN * dt_min)

            km = min(self.total_km, km + speed * (dt_min / 60.0))
            t_min += dt_min

            if km >= self.total_km and speed <= config.STOP_SNAP_SPEED_KMH:
                speed = 0.0

    def position_at(self, t_min: float) -> RoutePoint:
        if t_min <= self._schedule_t_min[0]:
            return self._schedule[0]
        if t_min >= self._schedule_t_min[-1]:
            return self._schedule[-1]

        # Binary search for the schedule sample at or after t_min.
        lo, hi = 0, len(self._schedule_t_min) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if self._schedule_t_min[mid] < t_min:
                lo = mid + 1
            else:
                hi = mid
        idx = lo
        if idx == 0:
            return self._schedule[0]

        t0, t1 = self._schedule_t_min[idx - 1], self._schedule_t_min[idx]
        p0, p1 = self._schedule[idx - 1], self._schedule[idx]
        frac = 0.0 if t1 == t0 else (t_min - t0) / (t1 - t0)
        return RoutePoint(
            lat=p0.lat + (p1.lat - p0.lat) * frac,
            lon=p0.lon + (p1.lon - p0.lon) * frac,
            speed_kmh=p0.speed_kmh + (p1.speed_kmh - p0.speed_kmh) * frac,
            km_travelled=p0.km_travelled + (p1.km_travelled - p0.km_travelled) * frac,
            nearest_waypoint=p0.nearest_waypoint if frac < 0.5 else p1.nearest_waypoint,
        )

    @property
    def duration_min(self) -> float:
        return self._schedule_t_min[-1]
