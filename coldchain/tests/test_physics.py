from __future__ import annotations

import math

from shared.enums import ProbePosition
from shared.profiles import MissionProfile, get_profile
from simulator import config
from simulator.ambient import ambient_c, effective_ambient_c
from simulator.route import Route, RoutePoint
from simulator.thermal import ThermalSim, stationary_capacity_frac

TUNIS = RoutePoint(lat=36.80, lon=10.18, speed_kmh=80.0, km_travelled=0.0, nearest_waypoint="Tunis")
MEDENINE = RoutePoint(
    lat=33.35, lon=10.50, speed_kmh=80.0, km_travelled=420.0, nearest_waypoint="Médenine"
)


def _stationary(point: RoutePoint) -> RoutePoint:
    return RoutePoint(
        lat=point.lat,
        lon=point.lon,
        speed_kmh=0.0,
        km_travelled=point.km_travelled,
        nearest_waypoint=point.nearest_waypoint,
    )


# --- route ---------------------------------------------------------------


def test_route_total_km_plausible_and_km_travelled_monotonic() -> None:
    route = Route()
    assert 450.0 <= route.total_km <= 600.0

    samples = [route.position_at(t).km_travelled for t in range(0, int(route.duration_min) + 1, 5)]
    assert all(b >= a for a, b in zip(samples, samples[1:], strict=False))


def test_speed_zero_during_configured_stop_and_resumes() -> None:
    route = Route()
    # Skip the first few minutes: the truck also starts from rest at Tunis,
    # which isn't the configured stop this test is looking for.
    stop_t = next(
        t
        for t in range(10, int(route.duration_min) + 1)
        if route.position_at(t).speed_kmh == 0.0
    )
    assert route.position_at(stop_t + 5).speed_kmh == 0.0
    later = route.position_at(stop_t + 20 + 15)
    assert later.speed_kmh > 60.0


# --- ambient ---------------------------------------------------------------


def test_ambient_medenine_hotter_than_tunis_at_midday() -> None:
    t_midday = 13 * 60
    assert ambient_c(t_midday, MEDENINE, departure_hour=0.0) > ambient_c(
        t_midday, TUNIS, departure_hour=0.0
    )


def test_ambient_early_morning_below_midafternoon() -> None:
    a_dawn = ambient_c(5 * 60, TUNIS, departure_hour=0.0)
    a_afternoon = ambient_c(15 * 60, TUNIS, departure_hour=0.0)
    assert a_dawn < a_afternoon


def test_effective_ambient_worse_when_stationary() -> None:
    t_solar_peak = int(config.SOLAR_PEAK_HOUR * 60)
    moving = effective_ambient_c(t_solar_peak, MEDENINE, departure_hour=0.0)
    stationary = effective_ambient_c(t_solar_peak, _stationary(MEDENINE), departure_hour=0.0)
    assert stationary > moving


# --- thermal ---------------------------------------------------------------


def test_cooling_holds_band_over_six_hours() -> None:
    profile = MissionProfile.pharma_refrigerated
    spec = get_profile(profile)
    sim = ThermalSim(profile)
    ambient_fixed_c = 35.0  # a warm, but not extreme, effective ambient

    for _ in range(6 * 60):
        state = sim.step(60.0, ambient_fixed_c, door_open=False)

    # After the run has settled, every probe should be inside (or very
    # close to) the profile band.
    margin = 0.5
    for temp in state.t_by_probe.values():
        assert spec.min_c - margin <= temp <= spec.max_c + margin


def test_cooling_off_warming_curve_fits_first_order_exponential() -> None:
    profile = MissionProfile.pharma_refrigerated
    sim = ThermalSim(profile)
    sim.cooling_capacity_frac = 0.0
    ambient_fixed_c = 30.0
    tau = config.THERMAL_TAU_MIN

    # BOTTOM has tau multiplier 1.0, so with cooling off its curve should
    # match a plain first-order exponential using the configured tau
    # directly (no compounding from a different probe's own multiplier).
    probe = ProbePosition.bottom
    offset = config.PROBE_OFFSET_C[probe]
    t0 = sim._t_probe[probe]  # noqa: SLF001 -- reading initial condition for the analytic check
    target = ambient_fixed_c + offset

    dt_s = 60.0
    dt_min = dt_s / 60.0
    n_steps = int(4 * tau / dt_min)
    max_rel_error = 0.0
    for i in range(1, n_steps + 1):
        state = sim.step(dt_s, ambient_fixed_c, door_open=False)
        t_elapsed = i * dt_min
        predicted = target - (target - t0) * math.exp(-t_elapsed / tau)
        span = abs(target - t0)
        rel_error = abs(state.t_by_probe[probe] - predicted) / span
        max_rel_error = max(max_rel_error, rel_error)

    assert max_rel_error <= 0.15


def test_rear_door_warmer_than_front_during_warm_run() -> None:
    profile = MissionProfile.pharma_refrigerated
    sim = ThermalSim(profile)
    ambient_fixed_c = 34.0

    for _ in range(3 * 60):
        state = sim.step(60.0, ambient_fixed_c, door_open=False)
        assert state.t_by_probe[ProbePosition.rear_door] > state.t_by_probe[ProbePosition.front]


def test_door_open_event_rises_monotonically_then_recovers() -> None:
    profile = MissionProfile.pharma_refrigerated
    sim = ThermalSim(profile)
    ambient_fixed_c = 32.0
    probe = ProbePosition.rear_door

    # Settle into steady operation first.
    for _ in range(2 * 60):
        sim.step(60.0, ambient_fixed_c, door_open=False)

    temps_during_open = []
    for _ in range(15):
        state = sim.step(60.0, ambient_fixed_c, door_open=True)
        temps_during_open.append(state.t_by_probe[probe])
    assert all(b >= a for a, b in zip(temps_during_open, temps_during_open[1:], strict=False))
    peak = temps_during_open[-1]

    for _ in range(2 * 60):
        state = sim.step(60.0, ambient_fixed_c, door_open=False)
    assert state.t_by_probe[probe] < peak


def test_cargo_daily_peak_lags_ambient_daily_peak() -> None:
    """Isolates thermal lag from every other confound.

    A moving route (like the preview run) never demonstrates this cleanly:
    the truck drives south into rising heat, so raw ambient keeps climbing
    for the whole trip and never turns over, and any door event dominates
    the cargo curve's shape. Here the vehicle is parked at a single
    waypoint for a full 24h so ambient completes one clean diurnal cycle
    with an unambiguous interior maximum, there are no door events, and
    cooling is off so cargo temperature freely tracks the thermal lag.

    The thermal model is still driven by effective_ambient_c (as real
    production code always drives it -- solar load included), but the
    reference point for "ambient's daily peak" is the raw air temperature,
    since that has one clean 15:00 maximum by construction. tau=120min
    implies a lag on the order of an hour or two for a diurnal-period
    forcing; 30-120 minutes is the sanity band for that.
    """
    profile = MissionProfile.pharma_refrigerated
    sim = ThermalSim(profile)
    sim.cooling_capacity_frac = 0.0  # cooling off: cargo freely follows ambient
    point = _stationary(TUNIS)  # parked -- "hold position fixed"
    departure_hour = 0.0
    dt_min = 5.0

    air_series: list[tuple[float, float]] = []
    cargo_series: list[tuple[float, float]] = []
    total_min = 24 * 60
    t = 0.0
    while t <= total_min:
        air = ambient_c(t, point, departure_hour)
        eff = effective_ambient_c(t, point, departure_hour)
        air_series.append((t, air))
        state = sim.step(dt_min * 60.0, eff, door_open=False)
        cargo_series.append((t, state.t_by_probe[ProbePosition.bottom]))
        t += dt_min

    ambient_peak_t, ambient_peak_c = max(air_series, key=lambda pair: pair[1])
    cargo_peak_t, cargo_peak_c = max(cargo_series, key=lambda pair: pair[1])
    lag_min = cargo_peak_t - ambient_peak_t

    print(
        f"\nambient daily peak: {ambient_peak_c:.2f} C at t={ambient_peak_t:.0f}min "
        f"({ambient_peak_t / 60:.2f}h)"
    )
    print(
        f"cargo daily peak:   {cargo_peak_c:.2f} C at t={cargo_peak_t:.0f}min "
        f"({cargo_peak_t / 60:.2f}h)"
    )
    print(f"lag: {lag_min:.0f} min")

    assert 30.0 <= lag_min <= 120.0, (
        f"expected cargo peak 30-120min after ambient peak (tau={config.THERMAL_TAU_MIN}min); "
        f"got {lag_min:.0f}min "
        f"(ambient peak t={ambient_peak_t:.0f}, cargo peak t={cargo_peak_t:.0f})"
    )


def test_stationary_capacity_frac_degrades_in_heat_but_has_a_floor() -> None:
    assert stationary_capacity_frac(80.0, 45.0) == 1.0
    assert stationary_capacity_frac(0.0, 20.0) == 1.0
    degraded = stationary_capacity_frac(0.0, 45.0)
    assert config.MIN_STATIONARY_CAPACITY_FRAC <= degraded < 1.0
