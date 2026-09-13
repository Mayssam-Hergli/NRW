"""M3 -- Mean Kinetic Temperature and the stability budget it consumes.

MKT (Haynes, 1971; adopted in USP <1150> / ICH Q1A) turns an uneven
temperature trace into the single constant temperature that would produce
the same cumulative thermal degradation, via the Arrhenius relationship.
It weights time at high temperature far more heavily than a simple mean
because degradation accelerates exponentially, not linearly, with heat:
two hours at 12 C and twenty-two at 5 C is not "a mean of 5.6 C" as far as
the product is concerned.

Honesty over completeness, throughout this module: a reading's value is
only ever assumed to hold until the *next* reading arrives, and only when
that next reading shows up within GAP_THRESHOLD_MIN. A longer gap between
two readings contributes to nothing -- not to MKT, not to time in or out
of band, not to coverage. It is dropped, not bridged. The last reading in
any series never gets a weight either, since there is no way to know how
long its value held afterward. This is deliberately conservative: an
unobserved period must never quietly read as a compliant (or non-compliant)
one, and it must never be smoothed away by assuming what happened during
it. See coverage_pct on BudgetResult.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from shared.enums import ProbePosition
from shared.profiles import MissionProfile, get_profile
from shared.schema import TelemetryPacket

# Gas constant, kJ/(mol*K).
_R_KJ_PER_MOL_K = 8.314462618e-3

# USP <1150>'s conventional default activation energy for MKT when a
# product's own value isn't known. This is a convention adopted across
# pharmaceutical stability programmes for general use, not a physical
# constant -- an API with a known, different activation energy should use
# that value instead; passing one is exactly what the parameter is for.
DEFAULT_ACTIVATION_ENERGY_KJ_MOL = 83.144

# A reading more than this many minutes from the next one is treated as a
# genuine, unobserved gap rather than a slower-but-legitimate sampling
# cadence. Comfortably above this project's typical ~1-minute telemetry
# interval (and above a plausible occasional multi-minute delay) while
# still well under a real connectivity outage -- e.g. the simulator's
# dead_zone scenario is configured for a 25-minute outage, but that outage
# can only run as long as the vehicle stays stopped, so it's actually
# observed at ~18 minutes; 15 catches that with margin. Tune per
# deployment if your device's normal cadence is coarser than this.
GAP_THRESHOLD_MIN = 15.0

# Illustrative reference shelf life at each profile's labelled storage
# temperature (its band midpoint), in days. These are demonstration
# assumptions for this project, not sourced from any real product's
# stability filing -- a production deployment would look up the actual
# labelled shelf life for the specific SKU being shipped.
REFERENCE_SHELF_LIFE_DAYS: dict[MissionProfile, float] = {
    MissionProfile.pharma_refrigerated: 730.0,
    MissionProfile.pharma_frozen: 1095.0,
    MissionProfile.controlled_room_temp: 1095.0,
    MissionProfile.vaccines: 365.0,
    MissionProfile.fresh_produce: 14.0,
}

# Minimum observed fraction of the shipment's nominal duration for a
# "compliant" verdict to even be on the table, regardless of temperature --
# an unobserved period is not a compliant one.
MIN_COVERAGE_PCT_FOR_COMPLIANT = 98.0

Reading = tuple[datetime, float]


class Verdict(StrEnum):
    compliant = "compliant"
    minor_deviation = "minor_deviation"
    excursion_review = "excursion_review"


@dataclass
class BudgetResult:
    mkt_c: float
    pct_consumed: float
    minutes_out_of_band_above: float
    minutes_out_of_band_below: float
    worst_excursion_c: float | None
    worst_excursion_duration_min: float
    coverage_pct: float
    verdict: Verdict


def _celsius_to_kelvin(c: float) -> float:
    return c + 273.15


def _sorted_distinct(readings: Sequence[Reading]) -> list[Reading]:
    if not readings:
        raise ValueError("at least one reading is required")
    return sorted(readings, key=lambda r: r[0])


def _valid_intervals(ordered: list[Reading]) -> list[tuple[Reading, float]]:
    """(reading, minutes-until-next) for every reading whose gap to the
    next one is within GAP_THRESHOLD_MIN. The last reading is never
    included (nothing follows it to bound an interval), and any reading
    whose *following* gap is a genuine outage is excluded too -- its own
    value is still real, it simply isn't credited with a duration it
    can't be shown to have held.
    """
    out: list[tuple[Reading, float]] = []
    for i in range(len(ordered) - 1):
        t_i, temp_i = ordered[i]
        t_next, _ = ordered[i + 1]
        gap_min = (t_next - t_i).total_seconds() / 60.0
        if gap_min <= GAP_THRESHOLD_MIN:
            out.append(((t_i, temp_i), gap_min))
    return out


def mean_kinetic_temperature(
    readings: list[Reading],
    activation_energy_kj_mol: float = DEFAULT_ACTIVATION_ENERGY_KJ_MOL,
) -> float:
    """Mean Kinetic Temperature, in Celsius, from unevenly-spaced readings.

        MKT = -Ea / (R * ln( sum(w_i * exp(-Ea / (R * T_i))) / sum(w_i) ))

    with T_i in Kelvin and w_i the minutes each reading is credited with
    (see module docstring: the interval to the next reading, dropped
    entirely across a gap wider than GAP_THRESHOLD_MIN, and zero for the
    final reading). A constant series returns that constant exactly; any
    non-constant series returns a value at or above the time-weighted
    arithmetic mean, since exp() is convex.
    """
    ordered = _sorted_distinct(readings)
    if len(ordered) == 1:
        return ordered[0][1]

    ea = activation_energy_kj_mol
    numerator = 0.0
    denominator = 0.0
    for (_, temp_c), weight_min in _valid_intervals(ordered):
        t_k = _celsius_to_kelvin(temp_c)
        numerator += weight_min * math.exp(-ea / (_R_KJ_PER_MOL_K * t_k))
        denominator += weight_min

    if denominator <= 0.0:
        # Every gap exceeded GAP_THRESHOLD_MIN (e.g. two isolated
        # readings with nothing connecting them): weighting can't
        # distinguish them, so fall back to an unweighted average rather
        # than dividing by zero.
        temps = [t for _, t in ordered]
        js = [math.exp(-ea / (_R_KJ_PER_MOL_K * _celsius_to_kelvin(t))) for t in temps]
        j_avg = sum(js) / len(js)
    else:
        j_avg = numerator / denominator

    return -ea / (_R_KJ_PER_MOL_K * math.log(j_avg)) - 273.15


def stability_budget_consumed(
    readings: list[Reading],
    profile: MissionProfile,
    shipment_duration_min: float,
    activation_energy_kj_mol: float = DEFAULT_ACTIVATION_ENERGY_KJ_MOL,
) -> BudgetResult:
    """Roll a reading series up into MKT, shelf-life consumed, time out of
    band, and a compliance verdict.

    pct_consumed models shelf life as a single Arrhenius rate relative to
    the profile's labelled storage temperature (its band midpoint): the
    reference shelf life (REFERENCE_SHELF_LIFE_DAYS, an illustrative
    assumption -- see its own docstring) is the time to consume 100% of
    shelf life while held exactly at that labelled temperature. At the
    shipment's actual MKT, the degradation rate scales by
    exp(Ea/R * (1/T_ref - 1/T_mkt)); pct_consumed is the shipment's
    duration at that scaled rate, as a percentage of the reference shelf
    life. This assumes single-step first-order Arrhenius kinetics hold
    across the whole observed temperature range, which is the same
    assumption MKT itself makes.
    """
    ordered = _sorted_distinct(readings)
    spec = get_profile(profile)

    mkt_c = mean_kinetic_temperature(readings, activation_energy_kj_mol)

    t_ref_k = _celsius_to_kelvin((spec.min_c + spec.max_c) / 2.0)
    t_mkt_k = _celsius_to_kelvin(mkt_c)
    rate_ratio = math.exp(
        (activation_energy_kj_mol / _R_KJ_PER_MOL_K) * (1.0 / t_ref_k - 1.0 / t_mkt_k)
    )
    shipment_duration_days = shipment_duration_min / (60.0 * 24.0)
    reference_shelf_life_days = REFERENCE_SHELF_LIFE_DAYS[profile]
    pct_consumed = 100.0 * shipment_duration_days * rate_ratio / reference_shelf_life_days

    minutes_above = 0.0
    minutes_below = 0.0
    observed_min = 0.0
    runs: list[dict[str, float]] = []
    current: dict[str, float] | None = None

    for (_, temp_c), weight_min in _valid_intervals(ordered):
        observed_min += weight_min
        if temp_c > spec.max_c:
            minutes_above += weight_min
            deviation = temp_c - spec.max_c
        elif temp_c < spec.min_c:
            minutes_below += weight_min
            deviation = spec.min_c - temp_c
        else:
            deviation = None

        if deviation is not None:
            if current is not None:
                current["duration"] += weight_min
                if deviation > current["peak_deviation"]:
                    current["peak_deviation"] = deviation
                    current["peak_c"] = temp_c
            else:
                current = {"duration": weight_min, "peak_c": temp_c, "peak_deviation": deviation}
        elif current is not None:
            runs.append(current)
            current = None
    if current is not None:
        runs.append(current)

    coverage_pct = (
        min(100.0, 100.0 * observed_min / shipment_duration_min)
        if shipment_duration_min > 0
        else 0.0
    )

    worst = max(runs, key=lambda r: r["peak_deviation"], default=None)
    worst_excursion_c = worst["peak_c"] if worst is not None else None
    worst_excursion_duration_min = worst["duration"] if worst is not None else 0.0

    total_out_of_band = minutes_above + minutes_below
    freeze_breach = spec.freeze_alarm and minutes_below > 0.0

    if freeze_breach:
        verdict = Verdict.excursion_review
    elif coverage_pct < MIN_COVERAGE_PCT_FOR_COMPLIANT:
        verdict = Verdict.excursion_review
    elif total_out_of_band <= 0.0:
        verdict = Verdict.compliant
    elif total_out_of_band <= spec.cumulative_excursion_limit_min:
        verdict = Verdict.minor_deviation
    else:
        verdict = Verdict.excursion_review

    return BudgetResult(
        mkt_c=mkt_c,
        pct_consumed=pct_consumed,
        minutes_out_of_band_above=minutes_above,
        minutes_out_of_band_below=minutes_below,
        worst_excursion_c=worst_excursion_c,
        worst_excursion_duration_min=worst_excursion_duration_min,
        coverage_pct=coverage_pct,
        verdict=verdict,
    )


def readings_from_packets(
    packets: list[TelemetryPacket],
    *,
    aggregate: Callable[[list[float]], float] = max,
    exclude_buffered: bool = True,
) -> list[Reading]:
    """Extract (ts, temperature) pairs from stored TelemetryPackets.

    `aggregate` reduces each packet's cargo readings (excluding
    ambient_external, which measures outside air, not cargo) to one value.
    Defaults to max -- the worst case for a heat excursion, which is the
    more common failure mode in this system. Pass `aggregate=min` when
    assessing a freeze-sensitive profile instead.

    Buffered packets are excluded by default. A buffered packet carries a
    genuinely measured value recovered after a connectivity outage, but
    that value was not verified in real time -- for compliance purposes
    this treats the outage window as unobserved (see coverage_pct) rather
    than silently counting a delayed recovery as equivalent to a live
    reading. Pass exclude_buffered=False to include them anyway.
    """
    out: list[Reading] = []
    for packet in packets:
        if exclude_buffered and packet.buffered:
            continue
        cargo_temps = [c.t_c for c in packet.cargo if c.pos != ProbePosition.ambient_external]
        if not cargo_temps:
            continue
        out.append((packet.ts, aggregate(cargo_temps)))
    return out
