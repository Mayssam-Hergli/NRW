"""Six scenarios driving the existing thermal and electrical sims over time.

Each scenario only sets ThermalSim/ElectricalSim parameters that already
exist (cooling_capacity_frac, setpoint_c, bearing_wear_factor,
unit_powered, ...) as a function of elapsed simulated time. No new physics
is added here -- the coupling between electrical strain and thermal effect
comes entirely from simulator/thermal.py and simulator/electrical.py.

run() yields TelemetryPackets in simulated chronological order. For
dead_zone, packets that fall inside the outage window are marked
buffered=True but are still yielded in that same chronological order --
actually withholding and replaying them late is simulator/publish.py's job
(the transport layer), not this module's.

ground_truth() returns the injected fault windows, the true parameter
trajectories, and the expected first-detection time: the validation set
steps 7-8 (M1, M2) are scored against.
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from shared.enums import CompressorState, GnssFix, ProbePosition
from shared.profiles import MissionProfile, get_profile
from shared.schema import (
    Band,
    CargoReading,
    Channel,
    DoorState,
    Gnss,
    Health,
    Motion,
    Power,
    TelemetryPacket,
)
from simulator import config
from simulator.ambient import ambient_c, effective_ambient_c
from simulator.electrical import ElectricalSim, ElectricalState
from simulator.route import Route, RoutePoint
from simulator.thermal import ThermalSim, ThermalState, stationary_capacity_frac

OUT_DIR = Path(__file__).parent / "out"

DEFAULT_DEVICE_ID = "TN-1234-GW"
BASE_TS = datetime(2026, 9, 14, 6, 0, 0, tzinfo=UTC)


def _make_gnss(point: RoutePoint) -> Gnss:
    return Gnss(lat=point.lat, lon=point.lon, speed_kmh=max(0.0, point.speed_kmh), fix=GnssFix.D3)


def _make_cargo(thermal_state: ThermalState) -> list[CargoReading]:
    return [
        CargoReading(
            tag="P-FRONT",
            pos=ProbePosition.front,
            t_c=round(thermal_state.t_by_probe[ProbePosition.front], 2),
        ),
        CargoReading(
            tag="P-REAR",
            pos=ProbePosition.rear_door,
            t_c=round(thermal_state.t_by_probe[ProbePosition.rear_door], 2),
        ),
        CargoReading(
            tag="P-TOP",
            pos=ProbePosition.top,
            t_c=round(thermal_state.t_by_probe[ProbePosition.top], 2),
        ),
        CargoReading(
            tag="P-BOTTOM",
            pos=ProbePosition.bottom,
            t_c=round(thermal_state.t_by_probe[ProbePosition.bottom], 2),
        ),
    ]


def _make_power(elec_state: ElectricalState, thermal_state: ThermalState) -> Power:
    if thermal_state.compressor_on and elec_state.i_compressor <= 0.0:
        state = CompressorState.FAULT
    elif thermal_state.compressor_on:
        state = CompressorState.RUN
    else:
        state = CompressorState.OFF
    return Power(
        v_bus=round(elec_state.v_bus, 2),
        compressor=Channel(
            i_rms=round(elec_state.i_compressor, 3),
            inrush_peak=round(elec_state.inrush_peak, 3) if elec_state.inrush_peak > 0 else None,
            duty_pct=round(elec_state.duty_pct, 2),
        ),
        cond_fan=Channel(i_rms=round(elec_state.i_cond_fan, 3)),
        evap_fan=Channel(i_rms=round(elec_state.i_evap_fan, 3)),
        state=state,
    )


class Scenario:
    """Base class. Subclasses set the class attributes and override
    _step_inject / _compute_ground_truth; everything else (route/ambient
    lookup, sim stepping, packet assembly, ground-truth caching) is shared.
    """

    name: str = "scenario"
    profile: MissionProfile = MissionProfile.pharma_refrigerated
    use_route: bool = True
    # Used only when use_route is False (long-haul degradation scenarios
    # that outlast the single ~7.5h corridor route): a fixed position and
    # the default duration for run()/ground_truth() when not overridden.
    stationary_lat_lon: tuple[float, float] = (34.74, 10.76)  # Sfax-ish
    stationary_speed_kmh: float = config.CRUISE_SPEED_KMH
    default_duration_min: float = 0.0

    def __init__(self, device_id: str = DEFAULT_DEVICE_ID) -> None:
        self.device_id = device_id
        self.shipment_id = f"SHIP-{self.name}-DEMO"
        self._route: Route | None = Route() if self.use_route else None
        self._cache_key: tuple[float, float] | None = None
        self._cached_ground_truth: dict | None = None

    def _resolve_duration_min(self, duration_min: float | None) -> float:
        if duration_min is not None:
            return duration_min
        if self.use_route:
            assert self._route is not None
            return self._route.duration_min
        return self.default_duration_min

    def _position_at(self, t_min: float) -> RoutePoint:
        if self.use_route:
            assert self._route is not None
            return self._route.position_at(t_min)
        lat, lon = self.stationary_lat_lon
        return RoutePoint(
            lat=lat,
            lon=lon,
            speed_kmh=self.stationary_speed_kmh,
            km_travelled=0.0,
            nearest_waypoint="corridor",
        )

    def _band(self) -> Band:
        spec = get_profile(self.profile)
        return Band(min_c=spec.min_c, max_c=spec.max_c)

    def _step_inject(
        self,
        t_min: float,
        thermal: ThermalSim,
        elec: ElectricalSim,
        point: RoutePoint,
        air_c: float,
    ) -> tuple[bool, dict]:
        """Mutate thermal/elec parameters for this step. Returns
        (door_open, fault_info); fault_info feeds both the packet (e.g.
        "buffered") and the trajectory sample recorded for ground_truth().
        """
        raise NotImplementedError

    def _buffer_pct(self, t_min: float) -> float:
        return 0.0

    def _compute_ground_truth(
        self, samples: list[dict], duration_min: float, dt_min: float
    ) -> dict:
        raise NotImplementedError

    def run(
        self, duration_min: float | None = None, dt_s: float = 60.0
    ) -> Iterator[TelemetryPacket]:
        duration = self._resolve_duration_min(duration_min)
        dt_min = dt_s / 60.0
        thermal = ThermalSim(self.profile)
        elec = ElectricalSim(self.profile)
        band = self._band()

        seq = 0
        door_events = 0
        prev_door_open = False
        t_min = 0.0
        samples: list[dict] = []

        while t_min <= duration:
            point = self._position_at(t_min)
            air = ambient_c(t_min, point, config.DEFAULT_DEPARTURE_HOUR)
            eff = effective_ambient_c(t_min, point, config.DEFAULT_DEPARTURE_HOUR)

            door_open, fault_info = self._step_inject(t_min, thermal, elec, point, air)
            if door_open and not prev_door_open:
                door_events += 1
            prev_door_open = door_open

            thermal_state = thermal.step(dt_s, eff, door_open=door_open)
            elec_state = elec.step(dt_s, eff, compressor_on=thermal_state.compressor_on)
            expected_duty = elec.expected_duty_pct(eff, point.speed_kmh)

            buffered = bool(fault_info.get("buffered", False))
            ts = BASE_TS + timedelta(minutes=t_min)

            packet = TelemetryPacket(
                device_id=self.device_id,
                shipment_id=self.shipment_id,
                mission_profile=self.profile,
                band=band,
                ts=ts,
                seq=seq,
                buffered=buffered,
                gnss=_make_gnss(point),
                cargo=_make_cargo(thermal_state),
                ambient_c=round(air, 2),
                door=DoorState(open=door_open, events=door_events),
                light_lux=0.0,
                motion=Motion(peak_g=fault_info.get("peak_g", 0.0), shock_events=0, vib_rms=0.02),
                power=_make_power(elec_state, thermal_state),
                health=Health(
                    batt_v=12.6,
                    rssi=-70,
                    buffer_pct=round(self._buffer_pct(t_min), 1),
                    gnss_fix=GnssFix.D3,
                ),
                sig=None,
            )

            samples.append(
                {
                    "t_min": t_min,
                    "cooling_capacity_frac": thermal.cooling_capacity_frac,
                    "setpoint_c": thermal.setpoint_c,
                    "bearing_wear_factor": elec.bearing_wear_factor,
                    "unit_powered": elec.unit_powered,
                    "door_open": door_open,
                    "buffered": buffered,
                    "worst_cargo_c": max(thermal_state.t_by_probe.values()),
                    "coldest_cargo_c": min(thermal_state.t_by_probe.values()),
                    "bottom_cargo_c": thermal_state.t_by_probe[ProbePosition.bottom],
                    "duty_pct": elec_state.duty_pct,
                    "expected_duty_pct": expected_duty,
                    "inrush_peak": elec_state.inrush_peak,
                    "i_compressor": elec_state.i_compressor,
                }
            )

            seq += 1
            yield packet
            t_min += dt_min

        self._cache_key = (duration, dt_s)
        self._cached_ground_truth = self._compute_ground_truth(samples, duration, dt_min)

    def ground_truth(self, duration_min: float | None = None, dt_s: float = 60.0) -> dict:
        resolved = self._resolve_duration_min(duration_min)
        if self._cached_ground_truth is None or self._cache_key != (resolved, dt_s):
            deque(self.run(duration_min, dt_s), maxlen=0)  # consume fully to populate the cache
        assert self._cached_ground_truth is not None
        return self._cached_ground_truth

    def write_ground_truth(
        self, out_dir: Path = OUT_DIR, duration_min: float | None = None, dt_s: float = 60.0
    ) -> Path:
        gt = self.ground_truth(duration_min, dt_s)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.name}_ground_truth.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(gt, f, indent=2)
        return path


class NominalScenario(Scenario):
    name = "nominal"
    profile = MissionProfile.pharma_refrigerated

    def _step_inject(self, t_min, thermal, elec, point, air_c):
        thermal.cooling_capacity_frac = stationary_capacity_frac(point.speed_kmh, air_c)
        return False, {}

    def _compute_ground_truth(self, samples, duration_min, dt_min):
        spec = get_profile(self.profile)
        minutes_outside_band = sum(
            dt_min for s in samples if not (spec.min_c <= s["worst_cargo_c"] <= spec.max_c)
        )
        return {
            "scenario": self.name,
            "profile": self.profile.value,
            "duration_min": duration_min,
            "dt_min": dt_min,
            "fault_windows": [],
            "expected_first_detection_min": None,
            "expected_detection_cause": None,
            "minutes_outside_band": minutes_outside_band,
            "trajectories": {
                "duty_pct": [round(s["duty_pct"], 2) for s in samples],
                "expected_duty_pct": [round(s["expected_duty_pct"], 2) for s in samples],
            },
            "notes": "Healthy run with the two routine offload stops baked into the "
            "route. Zero alerts expected.",
        }


class DoorOpenScenario(Scenario):
    name = "door_open"
    profile = MissionProfile.pharma_refrigerated
    DOOR_OPEN_DURATION_MIN = 18.0
    DOOR_OPEN_START_OFFSET_MIN = 2.0  # minutes into the Sfax stop before the door opens

    def __init__(self, device_id: str = DEFAULT_DEVICE_ID) -> None:
        super().__init__(device_id)
        self._stop_entered_t: float | None = None
        self._door_start_t: float | None = None

    def _step_inject(self, t_min, thermal, elec, point, air_c):
        thermal.cooling_capacity_frac = stationary_capacity_frac(point.speed_kmh, air_c)
        door_open = False
        if point.speed_kmh == 0.0 and t_min > 0.0:
            if self._stop_entered_t is None:
                self._stop_entered_t = t_min
            elapsed_in_stop = t_min - self._stop_entered_t
            if self._door_start_t is None and elapsed_in_stop >= self.DOOR_OPEN_START_OFFSET_MIN:
                self._door_start_t = t_min
            if (
                self._door_start_t is not None
                and t_min < self._door_start_t + self.DOOR_OPEN_DURATION_MIN
            ):
                door_open = True
        else:
            self._stop_entered_t = None
        return door_open, {}

    def _compute_ground_truth(self, samples, duration_min, dt_min):
        spec = get_profile(self.profile)
        door_samples = [s for s in samples if s["door_open"]]
        start = door_samples[0]["t_min"] if door_samples else None
        end = door_samples[-1]["t_min"] + dt_min if door_samples else None
        expected_detect = (start + spec.door_dwell_limit_min) if start is not None else None
        return {
            "scenario": self.name,
            "profile": self.profile.value,
            "duration_min": duration_min,
            "dt_min": dt_min,
            "fault_windows": (
                [{"start_min": start, "end_min": end, "cause": "door_unsecured"}]
                if start is not None
                else []
            ),
            "expected_first_detection_min": expected_detect,
            "expected_detection_cause": "door_unsecured",
            "notes": f"Door held open {self.DOOR_OPEN_DURATION_MIN} min at the Sfax stop; "
            f"suppressed until the profile's door_dwell_limit_min "
            f"({spec.door_dwell_limit_min} min).",
        }


class RefrigerantLossScenario(Scenario):
    name = "refrigerant_loss"
    profile = MissionProfile.pharma_refrigerated
    use_route = False  # multi-day decay outlasts the single ~7.5h corridor trip
    default_duration_min = 2880.0  # 2 days
    MIN_CAPACITY_FRAC = 0.3
    SMOOTH_WINDOW_MIN = 45.0  # trailing average window for the anomaly check

    def _step_inject(self, t_min, thermal, elec, point, air_c):
        duration = self.default_duration_min
        progress = min(1.0, t_min / duration)
        thermal.cooling_capacity_frac = 1.0 - progress * (1.0 - self.MIN_CAPACITY_FRAC)
        return False, {}

    def _compute_ground_truth(self, samples, duration_min, dt_min):
        spec = get_profile(self.profile)
        # Same rule as tests/test_electrical.py's lead-time test: the raw
        # rolling duty_pct has real cycle-to-cycle noise (the window
        # doesn't divide evenly into the compressor's natural cycle), so a
        # detector smooths over a trailing buffer spanning several cycles
        # before comparing to expected_duty_pct + margin.
        smooth_n = max(1, int(self.SMOOTH_WINDOW_MIN / dt_min))
        window_full_min = config.DUTY_CYCLE_WINDOW_MIN + self.SMOOTH_WINDOW_MIN
        buf: deque[float] = deque(maxlen=smooth_n)
        detect_t = None
        breach_t = None
        for s in samples:
            buf.append(s["duty_pct"])
            if s["t_min"] >= window_full_min and detect_t is None:
                smoothed = sum(buf) / len(buf)
                if smoothed - s["expected_duty_pct"] > config.DUTY_ANOMALY_MARGIN_PCT:
                    detect_t = s["t_min"]
            if breach_t is None and s["worst_cargo_c"] > spec.max_c:
                breach_t = s["t_min"]

        return {
            "scenario": self.name,
            "profile": self.profile.value,
            "duration_min": duration_min,
            "dt_min": dt_min,
            "fault_windows": [
                {
                    "start_min": 0.0,
                    "end_min": duration_min,
                    "cause": "refrigerant_loss",
                    "description": "cooling_capacity_frac decays linearly from 1.0 to "
                    f"{self.MIN_CAPACITY_FRAC}",
                }
            ],
            "trajectories": {
                "cooling_capacity_frac": [round(s["cooling_capacity_frac"], 4) for s in samples],
                "duty_pct": [round(s["duty_pct"], 2) for s in samples],
                "expected_duty_pct": [round(s["expected_duty_pct"], 2) for s in samples],
            },
            "expected_first_detection_min": detect_t,
            "expected_detection_cause": "refrigerant_loss",
            "expected_thermal_breach_min": breach_t,
            "notes": "Duty cycle should read anomalous well before any thermal breach "
            "(breach may not occur at all within duration_min).",
        }


class CompressorFailureScenario(Scenario):
    name = "compressor_failure"
    profile = MissionProfile.pharma_refrigerated
    BEARING_RAMP_START_MIN = 30.0
    BEARING_RAMP_END_MIN = 150.0
    BEARING_WEAR_MAX = 1.8
    FAILURE_AT_MIN = 240.0  # mid-transit
    BEARING_DETECT_MARGIN_FRAC = 0.15  # 15% over the healthy baseline inrush

    def _step_inject(self, t_min, thermal, elec, point, air_c):
        thermal.cooling_capacity_frac = stationary_capacity_frac(point.speed_kmh, air_c)
        if t_min < self.BEARING_RAMP_START_MIN:
            elec.bearing_wear_factor = 1.0
        elif t_min < self.BEARING_RAMP_END_MIN:
            frac = (t_min - self.BEARING_RAMP_START_MIN) / (
                self.BEARING_RAMP_END_MIN - self.BEARING_RAMP_START_MIN
            )
            elec.bearing_wear_factor = 1.0 + frac * (self.BEARING_WEAR_MAX - 1.0)
        else:
            elec.bearing_wear_factor = self.BEARING_WEAR_MAX

        elec.unit_powered = t_min < self.FAILURE_AT_MIN
        return False, {}

    def _compute_ground_truth(self, samples, duration_min, dt_min):
        baseline_inrush = next((s["inrush_peak"] for s in samples if s["inrush_peak"] > 0), None)
        bearing_detect_t = None
        if baseline_inrush:
            threshold = baseline_inrush * (1.0 + self.BEARING_DETECT_MARGIN_FRAC)
            for s in samples:
                if s["t_min"] >= self.BEARING_RAMP_START_MIN and s["inrush_peak"] > threshold:
                    bearing_detect_t = s["t_min"]
                    break
        unit_off_t = next((s["t_min"] for s in samples if not s["unit_powered"]), None)

        windows = [
            {
                "start_min": self.BEARING_RAMP_START_MIN,
                "end_min": self.FAILURE_AT_MIN,
                "cause": "bearing_wear",
            }
        ]
        if unit_off_t is not None:
            windows.append({"start_min": unit_off_t, "end_min": duration_min, "cause": "unit_off"})

        return {
            "scenario": self.name,
            "profile": self.profile.value,
            "duration_min": duration_min,
            "dt_min": dt_min,
            "fault_windows": windows,
            "trajectories": {
                "bearing_wear_factor": [round(s["bearing_wear_factor"], 3) for s in samples],
                "inrush_peak": [round(s["inrush_peak"], 2) for s in samples],
                "unit_powered": [s["unit_powered"] for s in samples],
            },
            "expected_first_detection_min": bearing_detect_t,
            "expected_detection_cause": "bearing_wear",
            "expected_second_detection_min": unit_off_t,
            "expected_second_detection_cause": "unit_off",
            "notes": "Early bearing-wear warning from rising inrush peak, then a hard "
            "unit_off when power is cut mid-transit.",
        }


class FreezeRiskScenario(Scenario):
    name = "freeze_risk"
    profile = MissionProfile.vaccines
    SETPOINT_DROP_START_MIN = 60.0
    LOW_SETPOINT_C = -1.0  # driver dialed the unit too cold
    EARLY_WARNING_MARGIN_C = 1.0  # alarm this many degrees above the true freeze floor
    # FRONT sits close to the evaporator with both a short tau and doubled
    # cooling (see thermal.py), so it swings several degrees below the
    # reference on every normal compressor cycle -- healthy operation on
    # this profile can instantaneously dip to ~2.5 C on its own, and during
    # a genuine fault it runs away so fast (both effects compounding) that
    # there's barely a minute between "distinguishable from noise" and
    # actual breach. BOTTOM (tau multiplier 1.0, matching the reference
    # exactly) is far calmer -- its own healthy minimum stays a full degree
    # above the warning threshold -- and gives a genuine multi-minute
    # margin during the real fault, so it stands in for "the cargo
    # temperature" here rather than the single coldest probe at each
    # instant.
    def _step_inject(self, t_min, thermal, elec, point, air_c):
        thermal.cooling_capacity_frac = stationary_capacity_frac(point.speed_kmh, air_c)
        if t_min >= self.SETPOINT_DROP_START_MIN:
            thermal.setpoint_c = self.LOW_SETPOINT_C
        return False, {}

    def _compute_ground_truth(self, samples, duration_min, dt_min):
        spec = get_profile(self.profile)
        warn_threshold = spec.min_c + self.EARLY_WARNING_MARGIN_C
        warn_t = None
        breach_t = None
        for s in samples:
            if warn_t is None and s["bottom_cargo_c"] <= warn_threshold:
                warn_t = s["t_min"]
            if breach_t is None and s["bottom_cargo_c"] < spec.min_c:
                breach_t = s["t_min"]
        return {
            "scenario": self.name,
            "profile": self.profile.value,
            "duration_min": duration_min,
            "dt_min": dt_min,
            "fault_windows": [
                {
                    "start_min": self.SETPOINT_DROP_START_MIN,
                    "end_min": duration_min,
                    "cause": "freeze_risk",
                    "description": f"setpoint lowered to {self.LOW_SETPOINT_C} C",
                }
            ],
            "expected_first_detection_min": warn_t,
            "expected_detection_cause": "freeze_risk",
            "expected_freeze_breach_min": breach_t,
            "notes": f"Lower-bound alarm should fire at {warn_threshold} C, before the "
            f"true {spec.min_c} C freeze floor is crossed.",
        }


class DeadZoneScenario(Scenario):
    name = "dead_zone"
    profile = MissionProfile.pharma_refrigerated
    OUTAGE_DURATION_MIN = 25.0
    OUTAGE_START_OFFSET_MIN = 2.0  # minutes into the Sfax stop before connectivity drops
    DOOR_OPEN_DURATION_MIN = 10.0  # within the outage window

    def __init__(self, device_id: str = DEFAULT_DEVICE_ID) -> None:
        super().__init__(device_id)
        self._stop_entered_t: float | None = None
        self._outage_start_t: float | None = None

    def _step_inject(self, t_min, thermal, elec, point, air_c):
        thermal.cooling_capacity_frac = stationary_capacity_frac(point.speed_kmh, air_c)
        door_open = False
        buffered = False
        if point.speed_kmh == 0.0 and t_min > 0.0:
            if self._stop_entered_t is None:
                self._stop_entered_t = t_min
            elapsed = t_min - self._stop_entered_t
            if self._outage_start_t is None and elapsed >= self.OUTAGE_START_OFFSET_MIN:
                self._outage_start_t = t_min
            if self._outage_start_t is not None:
                elapsed_outage = t_min - self._outage_start_t
                if elapsed_outage < self.OUTAGE_DURATION_MIN:
                    buffered = True
                    if elapsed_outage < self.DOOR_OPEN_DURATION_MIN:
                        door_open = True
        else:
            self._stop_entered_t = None
        return door_open, {"buffered": buffered}

    def _buffer_pct(self, t_min: float) -> float:
        if self._outage_start_t is not None:
            elapsed = t_min - self._outage_start_t
            if 0.0 <= elapsed < self.OUTAGE_DURATION_MIN:
                return min(80.0, (elapsed / self.OUTAGE_DURATION_MIN) * 80.0)
        return 0.0

    def _compute_ground_truth(self, samples, duration_min, dt_min):
        buffered_samples = [s for s in samples if s["buffered"]]
        start = buffered_samples[0]["t_min"] if buffered_samples else None
        end = buffered_samples[-1]["t_min"] + dt_min if buffered_samples else None
        ts_values = [s["t_min"] for s in samples]
        gap = any(b - a > dt_min * 1.5 for a, b in zip(ts_values, ts_values[1:], strict=False))
        return {
            "scenario": self.name,
            "profile": self.profile.value,
            "duration_min": duration_min,
            "dt_min": dt_min,
            "fault_windows": (
                [
                    {
                        "start_min": start,
                        "end_min": end,
                        "cause": None,
                        "description": "gateway offline (no connectivity); "
                        "packets buffered locally",
                    }
                ]
                if start is not None
                else []
            ),
            "expected_first_detection_min": None,
            "expected_detection_cause": None,
            "expected_gap_in_record": gap,
            "notes": "Outage packets are marked buffered=True with correct original "
            "timestamps; once ingested, the record should show no coverage gap. The "
            "concurrent door-open event during the outage is buffered along with "
            "everything else.",
        }


SCENARIOS: dict[str, type[Scenario]] = {
    "nominal": NominalScenario,
    "door_open": DoorOpenScenario,
    "refrigerant_loss": RefrigerantLossScenario,
    "compressor_failure": CompressorFailureScenario,
    "freeze_risk": FreezeRiskScenario,
    "dead_zone": DeadZoneScenario,
}


def write_all_ground_truth(out_dir: Path = OUT_DIR) -> list[Path]:
    return [cls().write_ground_truth(out_dir) for cls in SCENARIOS.values()]


if __name__ == "__main__":
    for written in write_all_ground_truth():
        print(f"wrote {written}")
