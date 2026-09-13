"""M1 -- thermal breach forecast, edge + cloud.

Answers one question: how many minutes until cargo crosses the band. This
is the number in "Depassement dans 38 min."

    dT/dt = (T_eff - T) / tau - cooling_delivered

M1 never imports simulator.config or simulator.thermal -- on real hardware
there is no ground-truth tau to read, so every physical constant here is
either read from the telemetry contract (shared/schema.py, shared/profiles.py
-- the device's actual inputs) or an independent prior M1 owns itself,
documented as such below.

--- Tau calibration -------------------------------------------------------

Every door-open event is a free experiment: cooling drops out and the
compartment relaxes toward ambient, so the warming curve reveals tau
directly (PROJECT.md's own calibration story). This module fits it with
online recursive least squares (RLS), per probe, then combines the four
into one estimate.

One wrinkle the door-open window itself introduces: an open door creates
turbulent mixing that equilibrates *faster* than the sealed, still-air
tau relevant to normal (closed-door) forecasting -- a real physical effect,
not just a simulator choice (see DOOR_OPEN_MIXING_FACTOR below). RLS fits
the *open-door* time constant directly from the data; multiplying by the
assumed mixing factor converts it back to the closed-door tau used for
forecasting the rest of the trip.

Per probe, RLS fits a 2-parameter model y = a*x + c, where x = (ambient_eff
- T_prev), y = (T_now - T_prev)/dt, a = 1/tau_open, and c absorbs that
probe's own steady-state offset (each probe warms toward a slightly
different target -- closer to the door, closer to the evaporator -- so a
shared intercept across probes would be mis-specified; each probe keeps its
own). tau_estimate_min is the mean of 1/a across probes, converted via the
mixing factor.

--- Per-probe forecasting --------------------------------------------------

Per-probe minutes_to_breach does *not* need a separately-fitted per-probe
tau: each probe's own most-recent observed trend (a short rolling-window
slope) already reflects its own true dynamics, including whatever makes
REAR_DOOR run warmer and closer to breach than FRONT. The forecast backs out
an implied local steady-state target from (current reading, current trend,
shared tau) and projects the same first-order exponential forward from
there -- exact for constant ambient, and swapped for a step-by-step forward
simulation when a future ambient sequence is supplied (`ambient_forecast`).

--- Effective ambient -------------------------------------------------------

The device measures raw outside air temperature, not "effective ambient" --
solar loading and parked-vs-moving airflow are physical effects it has to
estimate itself. `_effective_ambient_c` is M1's own independent estimate
(bell-curve solar intensity around midday, worse while stationary), built
only from telemetry (packet timestamp, GNSS speed) -- not imported from the
simulator. Its constants are a first-cut assumption a real deployment would
calibrate per vehicle/body colour, not a read of the simulator's own values.

--- Edge / state size -------------------------------------------------------

Runs as plain arithmetic -- no numpy, scipy, or fitting library. Per probe:
one RLS state (a, c, and a symmetric 2x2 covariance -- 5 floats) plus a
capped rolling window of the last TREND_WINDOW_SAMPLES (timestamp, reading)
pairs for the local slope estimate. Four probes plus a handful of scalars
(door-event count, previous sample) is on the order of 150 floats total,
independent of trip length -- it does not grow over a 9-hour run.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from shared.enums import ProbePosition
from shared.schema import TelemetryPacket

ALL_PROBES: tuple[ProbePosition, ...] = (
    ProbePosition.front,
    ProbePosition.rear_door,
    ProbePosition.top,
    ProbePosition.bottom,
)

# --- M1's own priors and assumptions, independent of the simulator --------

PRIOR_TAU_MIN = 90.0
PRIOR_CONFIDENCE = 0.1

# An open door's turbulent mixing accelerates equilibration relative to the
# sealed, still-air state. A real deployment would calibrate this once per
# vehicle body style on a bench (time a probe's warming with the door
# propped open vs. closed at a known ambient delta); taken here as a
# reasonable first-cut assumption, not read from the simulator.
DOOR_OPEN_MIXING_FACTOR = 3.0

# Spans several compressor duty cycles (~9-15min each), not just one -- a
# shorter window regresses over a single on/off swing and reads pure cycle
# noise as a secular trend, producing spurious breach forecasts on a
# perfectly healthy, band-holding nominal run. Wider still (e.g. 45) is
# safer against noise but reacts too slowly to a fast-onset fault like
# freeze_risk's runaway, which leaves only a few minutes of true margin --
# 30 is the empirical balance: zero false positives across a full nominal
# run, while still catching freeze_risk before its breach.
TREND_WINDOW_SAMPLES = 30
MIN_TREND_SAMPLES = TREND_WINDOW_SAMPLES  # require the full window, not a partial one
MAX_SANE_DT_MIN = 10.0  # guards a single bad finite-difference sample
# t-stat floor for trusting a window's slope; nominal's noise floor peaks
# under 2.5 (see _slope docstring), so this clears it with margin.
TREND_TSTAT_MIN = 4.0

# A forecast this far out is not the countdown the driver needs -- it's an
# extrapolation of the *current* trend holding constant, which for a slowly
# worsening fault (e.g. a decaying refrigerant leak) understates how much
# worse things get before breach: the earliest statistically-significant
# trend on a multi-day decay is visible many hours ahead, but a fixed-target
# exponential fit that far out misses by hours, not minutes. Past this
# horizon, the right answer is a qualitative "predictive window" (which
# fusion/M2 already carries), not a specific ETA M1 can't actually back up.
MAX_FORECAST_HORIZON_MIN = 40.0

# M1's own solar-load estimate -- shape only (bell curve at midday, worse
# parked than moving), not values read from simulator.ambient/config.
SOLAR_PEAK_HOUR_UTC = 13.0
SOLAR_HALF_WIDTH_HOURS = 6.5
SOLAR_BUMP_MOVING_C = 6.0
SOLAR_BUMP_STATIONARY_C = 10.0
STATIONARY_SPEED_KMH = 2.0

FORECAST_DT_MIN = 1.0
FORECAST_MAX_STEPS = 720  # 12h cap on the forward simulation


def _hour_of_day_utc(ts: datetime) -> float:
    return ts.hour + ts.minute / 60.0 + ts.second / 3600.0


def _solar_intensity(hour: float) -> float:
    delta = ((hour - SOLAR_PEAK_HOUR_UTC + 12.0) % 24.0) - 12.0
    if abs(delta) >= SOLAR_HALF_WIDTH_HOURS:
        return 0.0
    return math.cos((math.pi / 2.0) * (delta / SOLAR_HALF_WIDTH_HOURS))


def _effective_ambient_c(ambient_c: float, ts: datetime, speed_kmh: float) -> float:
    hour = _hour_of_day_utc(ts)
    intensity = _solar_intensity(hour)
    moving = speed_kmh > STATIONARY_SPEED_KMH
    bump = SOLAR_BUMP_MOVING_C if moving else SOLAR_BUMP_STATIONARY_C
    return ambient_c + bump * intensity


@dataclass
class _RLS2:
    """Two-parameter recursive least squares: y = a*x + c.

    State is the full footprint: a, c, and a symmetric 2x2 covariance
    (p00, p01, p11) -- 5 floats. No forgetting factor (lambda=1): each
    instance lives for one vehicle/trip, so plain convergence is preferred
    over drift-tracking.
    """

    a: float
    c: float = 0.0
    p00: float = 1.0e4
    p01: float = 0.0
    p11: float = 1.0e4

    def update(self, x: float, y: float) -> None:
        px0 = self.p00 * x + self.p01
        px1 = self.p01 * x + self.p11
        denom = 1.0 + x * px0 + px1
        if denom <= 0:
            return
        k0 = px0 / denom
        k1 = px1 / denom
        err = y - (self.a * x + self.c)
        self.a += k0 * err
        self.c += k1 * err
        self.p00 -= k0 * px0
        self.p01 -= k0 * px1
        self.p11 -= k1 * px1


@dataclass
class ForecastResult:
    minutes_to_breach: float | None
    breach_bound: str | None
    tau_estimate_min: float
    tau_confidence: float
    per_probe: dict[ProbePosition, float | None]
    trend_c_per_min: float


def _time_to_cross(
    t0: float, target: float, tau: float, bound: float, direction: str
) -> float | None:
    """Minutes for the exponential T(t) = target - (target-t0)*exp(-t/tau)
    to reach `bound` from `t0`, given the caller already knows which way it's
    trending (direction="upper" warming toward bound=max_c, "lower" cooling
    toward bound=min_c). None if the steady state never actually gets past
    the bound; 0.0 if it's already past it."""
    if direction == "upper":
        if t0 >= bound:
            return 0.0
        if target <= bound or target <= t0:
            return None
    else:
        if t0 <= bound:
            return 0.0
        if target >= bound or target >= t0:
            return None

    ratio = (target - bound) / (target - t0)
    if ratio <= 0.0 or ratio >= 1.0:
        return None
    return -tau * math.log(ratio)


class M1ThermalForecast:
    """One instance per device/trip. Feed packets in chronological order
    (packet.ts drives all timing, so buffered/replayed packets are fine as
    long as they arrive in their original order)."""

    def __init__(self) -> None:
        prior_a = DOOR_OPEN_MIXING_FACTOR / PRIOR_TAU_MIN
        self._door_rls: dict[ProbePosition, _RLS2] = {p: _RLS2(a=prior_a) for p in ALL_PROBES}
        self._history: dict[ProbePosition, deque[tuple[float, float]]] = {
            p: deque(maxlen=TREND_WINDOW_SAMPLES) for p in ALL_PROBES
        }
        self._prev_ts: datetime | None = None
        self._prev_t: dict[ProbePosition, float] = {}
        self._prev_door_open = False
        self._door_events_seen = 0

    def _tau_estimate_min(self) -> float:
        a_vals = [max(rls.a, 1e-6) for rls in self._door_rls.values()]
        mean_a = sum(a_vals) / len(a_vals)
        return DOOR_OPEN_MIXING_FACTOR / mean_a

    def _tau_confidence(self) -> float:
        if self._door_events_seen == 0:
            return PRIOR_CONFIDENCE
        return min(0.95, 0.5 + 0.15 * (self._door_events_seen - 1))

    def _slope(self, probe: ProbePosition) -> float | None:
        """Least-squares slope of the rolling window, gated by its own
        t-statistic (slope / standard error). A single duty cycle inside the
        window is enough noise that raw slope alone is a poor discriminator
        -- on a healthy nominal run its t-stat never exceeds ~2.5, while a
        real, sustained trend (door-open, refrigerant creep) separates from
        that noise floor well before its slope magnitude alone would."""
        hist = self._history[probe]
        if len(hist) < MIN_TREND_SAMPLES:
            return None
        n = len(hist)
        t_mean = sum(t for t, _ in hist) / n
        v_mean = sum(v for _, v in hist) / n
        sxx = sum((t - t_mean) ** 2 for t, _ in hist)
        sxy = sum((t - t_mean) * (v - v_mean) for t, v in hist)
        if sxx < 1e-9:
            return None
        slope = sxy / sxx
        resid_var = sum((v - (v_mean + slope * (t - t_mean))) ** 2 for t, v in hist) / (n - 2)
        if resid_var <= 0.0:
            return slope
        se = math.sqrt(resid_var / sxx)
        if se < 1e-12 or abs(slope) / se < TREND_TSTAT_MIN:
            return None
        return slope

    def update(
        self,
        packet: TelemetryPacket,
        ambient_forecast: list[float] | None = None,
    ) -> ForecastResult:
        eff_ambient = _effective_ambient_c(packet.ambient_c, packet.ts, packet.gnss.speed_kmh)
        t_min_now = packet.ts.timestamp() / 60.0
        door_open = packet.door.open

        cargo_by_probe = {c.pos: c.t_c for c in packet.cargo if c.pos in self._door_rls}

        dt_min: float | None = None
        if self._prev_ts is not None:
            dt = (packet.ts - self._prev_ts).total_seconds() / 60.0
            if 0 < dt <= MAX_SANE_DT_MIN:
                dt_min = dt

        if dt_min is not None and door_open and self._prev_door_open:
            for probe, t_now in cargo_by_probe.items():
                t_prev = self._prev_t.get(probe)
                if t_prev is None:
                    continue
                x = eff_ambient - t_prev
                y = (t_now - t_prev) / dt_min
                self._door_rls[probe].update(x, y)

        if door_open and not self._prev_door_open:
            self._door_events_seen += 1

        for probe, t_now in cargo_by_probe.items():
            self._history[probe].append((t_min_now, t_now))

        self._prev_t = dict(cargo_by_probe)
        self._prev_door_open = door_open
        self._prev_ts = packet.ts

        tau = self._tau_estimate_min()
        confidence = self._tau_confidence()

        # Both bounds are always watched, regardless of freeze_alarm: it's a
        # severity/alerting distinction downstream (fusion), not a reason
        # for M1 itself to stay blind to a lower-bound trend.
        band = packet.band

        per_probe: dict[ProbePosition, float | None] = {}
        headline_min: float | None = None
        headline_bound: str | None = None
        headline_trend = 0.0

        for probe in ALL_PROBES:
            t_now = cargo_by_probe.get(probe)
            per_probe[probe] = None
            if t_now is None or band is None:
                continue

            if door_open:
                # Physics mode: while the door is actually open, cooling is
                # known to be ~0 and this probe's own open-door (tau, offset)
                # is already known from its RLS fit -- no need to wait for a
                # windowed trend to accumulate statistical significance, which
                # would react far slower than the 15-20min a door-open event
                # typically lasts.
                rls = self._door_rls[probe]
                a = rls.a if rls.a > 1e-6 else 1e-6
                fit_tau = 1.0 / a
                implied_target = eff_ambient + rls.c / a
                slope = (implied_target - t_now) / fit_tau
            else:
                slope = self._slope(probe)
                if slope is None:
                    continue
                fit_tau = tau
                implied_target = t_now + slope * fit_tau

            bias = implied_target - eff_ambient

            result_min: float | None = None
            bound_dir: str | None = None

            if slope > 1e-6:
                if ambient_forecast:
                    result_min = self._simulate_forward(
                        t_now, bias, fit_tau, band.max_c, ambient_forecast, "upper"
                    )
                else:
                    result_min = _time_to_cross(t_now, implied_target, fit_tau, band.max_c, "upper")
                bound_dir = "upper"
            elif slope < -1e-6:
                if ambient_forecast:
                    result_min = self._simulate_forward(
                        t_now, bias, fit_tau, band.min_c, ambient_forecast, "lower"
                    )
                else:
                    result_min = _time_to_cross(t_now, implied_target, fit_tau, band.min_c, "lower")
                bound_dir = "lower"

            if result_min is not None and result_min > MAX_FORECAST_HORIZON_MIN:
                result_min = None

            per_probe[probe] = result_min
            if result_min is not None and (headline_min is None or result_min < headline_min):
                headline_min = result_min
                headline_bound = bound_dir
                headline_trend = slope

        return ForecastResult(
            minutes_to_breach=headline_min,
            breach_bound=headline_bound,
            tau_estimate_min=tau,
            tau_confidence=confidence,
            per_probe=per_probe,
            trend_c_per_min=headline_trend,
        )

    @staticmethod
    def _simulate_forward(
        t0: float,
        bias: float,
        tau: float,
        bound: float,
        ambient_forecast: list[float],
        direction: str,
    ) -> float | None:
        """Forward-Euler the same ODE minute by minute against a supplied
        future ambient sequence, holding this probe's own (offset -
        cooling*tau) bias constant. Falls back to the closed form when no
        forecast is given (see _time_to_cross)."""
        if direction == "upper" and t0 >= bound:
            return 0.0
        if direction == "lower" and t0 <= bound:
            return 0.0

        t = t0
        steps = min(len(ambient_forecast), FORECAST_MAX_STEPS)
        for i in range(steps):
            target = ambient_forecast[i] + bias
            t_new = t + FORECAST_DT_MIN * (target - t) / tau
            crossed = (t <= bound <= t_new) or (t_new <= bound <= t)
            if crossed:
                span = t_new - t
                frac = 0.0 if abs(span) < 1e-9 else (bound - t) / span
                return i * FORECAST_DT_MIN + frac * FORECAST_DT_MIN
            t = t_new
        return None
