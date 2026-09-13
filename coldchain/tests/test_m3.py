from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ingest.store import Store
from models.m3_mkt import (
    Verdict,
    mean_kinetic_temperature,
    readings_from_packets,
    stability_budget_consumed,
)
from shared.profiles import MissionProfile, get_profile
from simulator.scenarios import DeadZoneScenario, NominalScenario

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _weighted_arithmetic_mean(readings: list[tuple[datetime, float]]) -> float:
    """Same interval-to-next weighting as mean_kinetic_temperature, but a
    plain (non-Arrhenius) average -- used as the comparison baseline.
    """
    ordered = sorted(readings, key=lambda r: r[0])
    total_w = 0.0
    total_wt = 0.0
    for i in range(len(ordered) - 1):
        t_i, temp_i = ordered[i]
        t_next, _ = ordered[i + 1]
        w = (t_next - t_i).total_seconds() / 60.0
        total_w += w
        total_wt += w * temp_i
    return total_wt / total_w


def test_mkt_of_constant_series_equals_that_temperature() -> None:
    readings = [(BASE + timedelta(minutes=i), 5.0) for i in range(10)]
    assert mean_kinetic_temperature(readings) == pytest.approx(5.0, abs=1e-9)


def test_mkt_alternating_series_exceeds_arithmetic_mean() -> None:
    temps = [2.0, 8.0] * 20
    readings = [(BASE + timedelta(minutes=i), t) for i, t in enumerate(temps)]
    mkt = mean_kinetic_temperature(readings)
    assert mkt > _weighted_arithmetic_mean(readings)


def test_mkt_two_hours_hot_gap_widens_with_activation_energy() -> None:
    # Two hours at 12 C, then twenty-two at 5 C (hourly samples), plus one
    # trailing point to bound the last hourly interval (dropped from
    # weighting per the module's own convention).
    times = [BASE + timedelta(minutes=60 * i) for i in range(25)]
    temps = [12.0, 12.0] + [5.0] * 22 + [5.0]
    readings = list(zip(times, temps, strict=True))

    arithmetic_mean = _weighted_arithmetic_mean(readings)
    mkt_default = mean_kinetic_temperature(readings)
    mkt_high_ea = mean_kinetic_temperature(readings, activation_energy_kj_mol=120.0)

    assert arithmetic_mean == pytest.approx(5.5833, abs=0.001)
    assert mkt_default > arithmetic_mean + 0.05

    gap_default = mkt_default - arithmetic_mean
    gap_high = mkt_high_ea - arithmetic_mean
    assert gap_high > gap_default


def test_mkt_uneven_spacing_weights_by_interval() -> None:
    # Series A: a single hot reading held for a 10-minute interval.
    series_a = [
        (BASE, 5.0),
        (BASE + timedelta(minutes=1), 8.0),
        (BASE + timedelta(minutes=11), 5.0),
        (BASE + timedelta(minutes=12), 5.0),  # trailing point, dropped
    ]
    # Series B: the same total hot exposure as ten evenly-spaced 1-minute
    # hot readings instead of one long-interval one.
    series_b = [(BASE, 5.0)]
    series_b += [(BASE + timedelta(minutes=1 + i), 8.0) for i in range(10)]
    series_b += [(BASE + timedelta(minutes=11), 5.0), (BASE + timedelta(minutes=12), 5.0)]

    assert mean_kinetic_temperature(series_a) == pytest.approx(
        mean_kinetic_temperature(series_b), abs=1e-9
    )


def test_compliant_on_stored_nominal_scenario(tmp_path) -> None:
    store = Store.open(tmp_path / "test.db")
    scenario = NominalScenario()
    packets = list(scenario.run(dt_s=60.0))
    for packet in packets:
        store.insert_packet(packet)

    stored = store.shipment(scenario.shipment_id)
    readings = readings_from_packets(stored)
    duration_min = (stored[-1].ts - stored[0].ts).total_seconds() / 60.0

    result = stability_budget_consumed(readings, scenario.profile, duration_min)

    assert result.minutes_out_of_band_above == 0.0
    assert result.minutes_out_of_band_below == 0.0
    assert result.coverage_pct >= 99.0
    assert result.verdict == Verdict.compliant


def _band_excursion_readings(
    profile: MissionProfile, excursion_minutes: int, excursion_delta_c: float
) -> list[tuple[datetime, float]]:
    spec = get_profile(profile)
    mid = (spec.min_c + spec.max_c) / 2.0
    if excursion_delta_c > 0:
        excursion_temp = spec.max_c + excursion_delta_c
    else:
        excursion_temp = spec.min_c + excursion_delta_c

    readings = []
    t = BASE
    for _ in range(30):
        readings.append((t, mid))
        t += timedelta(minutes=1)
    for _ in range(excursion_minutes):
        readings.append((t, excursion_temp))
        t += timedelta(minutes=1)
    for _ in range(31):
        readings.append((t, mid))
        t += timedelta(minutes=1)
    return readings


def test_minor_deviation_on_excursion_under_limit() -> None:
    profile = MissionProfile.pharma_refrigerated
    spec = get_profile(profile)
    assert spec.cumulative_excursion_limit_min == 30

    readings = _band_excursion_readings(profile, excursion_minutes=12, excursion_delta_c=1.0)
    duration_min = (readings[-1][0] - readings[0][0]).total_seconds() / 60.0

    result = stability_budget_consumed(readings, profile, duration_min)

    assert result.minutes_out_of_band_above == pytest.approx(12.0, abs=0.01)
    assert result.verdict == Verdict.minor_deviation


def test_excursion_review_when_limit_exceeded() -> None:
    profile = MissionProfile.pharma_refrigerated
    spec = get_profile(profile)
    over_limit_minutes = spec.cumulative_excursion_limit_min + 10

    readings = _band_excursion_readings(
        profile, excursion_minutes=over_limit_minutes, excursion_delta_c=1.0
    )
    duration_min = (readings[-1][0] - readings[0][0]).total_seconds() / 60.0

    result = stability_budget_consumed(readings, profile, duration_min)

    assert result.minutes_out_of_band_above == pytest.approx(float(over_limit_minutes), abs=0.01)
    assert result.verdict == Verdict.excursion_review


def test_lower_bound_breach_on_vaccines_is_excursion_review_never_minor() -> None:
    profile = MissionProfile.vaccines
    spec = get_profile(profile)
    assert spec.freeze_alarm is True

    # A short freeze dip -- well under the profile's own excursion limit --
    # should still never be "minor" on a freeze-alarm profile.
    readings = _band_excursion_readings(profile, excursion_minutes=3, excursion_delta_c=-1.0)
    duration_min = (readings[-1][0] - readings[0][0]).total_seconds() / 60.0

    result = stability_budget_consumed(readings, profile, duration_min)

    assert result.minutes_out_of_band_below > 0.0
    assert result.minutes_out_of_band_below <= spec.cumulative_excursion_limit_min
    assert result.verdict == Verdict.excursion_review


def test_coverage_drops_with_gap_and_nothing_is_interpolated() -> None:
    readings = [(BASE + timedelta(minutes=i), 5.0) for i in range(10)]
    readings.append((BASE + timedelta(minutes=10 + 25), 5.0))  # a 25-minute gap
    readings.append((BASE + timedelta(minutes=10 + 25 + 5), 5.0))
    original_len = len(readings)
    duration_min = (readings[-1][0] - readings[0][0]).total_seconds() / 60.0

    result = stability_budget_consumed(readings, MissionProfile.pharma_refrigerated, duration_min)

    assert len(readings) == original_len  # nothing was inserted to fill the gap
    assert result.coverage_pct == pytest.approx(35.0, abs=0.5)
    assert result.coverage_pct < 100.0


def test_dead_zone_stored_shipment_coverage_below_100_affects_verdict(tmp_path) -> None:
    store = Store.open(tmp_path / "test.db")
    scenario = DeadZoneScenario()
    packets = list(scenario.run(dt_s=60.0))
    for packet in packets:
        store.insert_packet(packet)

    stored = store.shipment(scenario.shipment_id)
    assert any(p.buffered for p in stored), "scenario should have produced buffered packets"

    readings = readings_from_packets(stored, exclude_buffered=True)
    duration_min = (stored[-1].ts - stored[0].ts).total_seconds() / 60.0

    result = stability_budget_consumed(readings, scenario.profile, duration_min)

    assert result.coverage_pct < 100.0
    assert result.verdict != Verdict.compliant
