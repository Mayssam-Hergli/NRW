"""Fusion -- cross-modal disambiguation.

fuse() is a pure function: given the current packet, this instant's M1/M2/M3
outputs, and a rolling window of recent packets for the same device, it
returns one Diagnosis. It holds no state of its own -- door-dwell duration
is recovered from `history` each call (see _door_open_duration_min) rather
than tracked internally, so this module stays trivially testable with a
synthetic packet list and safely reusable if the caller ever needs to
re-run it. models/alert_engine.py owns the actual alert lifecycle (when a
Diagnosis becomes a new AlertRecord vs. an update vs. a resolution).

The quadrant (current normal/abnormal x temp in-band/drifting) is the
product's core claim: the same thermal signature means something completely
different depending on what the other three sensor domains say. Every
branch below is one cell of that quadrant, disambiguated further by door
and speed state.

Deliberate deviation from a literal reading of the fields list: cause,
severity and prescribed_action are all `| None` here even where the
originating enums have no "nothing to report" member. A healthy packet or a
suppressed offload stop genuinely has no action to prescribe -- inventing
one from PrescribedAction's 14 members to satisfy a non-optional type would
be actively misleading, which is exactly what this project's own honesty
rules argue against.

Known gap: "remaining journey time" is named as a severity input but isn't
available anywhere in TelemetryPacket or the models feeding fuse() --
there's no ETA/route-remaining field in the frozen contract. Severity below
uses what's actually observable (M1's countdown, distance to band edge as a
fraction of band width -- which already answers "how tight is this
profile's tolerance" -- and ambient heat) and does not claim to use journey
time.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from models.electrical_health import ElectricalHealthResult
from models.m1_thermal import ForecastResult
from models.m3_mkt import BudgetResult
from shared.enums import FaultCause, PrescribedAction, ProbePosition, Severity
from shared.profiles import ProfileSpec, get_profile
from shared.schema import TelemetryPacket

# A device parked with the door open for a legitimate delivery has light
# flooding in -- PROJECT.md puts this at "tens of thousands of lux"; a
# sealed, dark compartment reads at or near zero. This threshold only needs
# to sit somewhere in the wide gap between those two regimes.
LIGHT_DETECTED_LUX_THRESHOLD = 50.0

# Matches the convention used elsewhere (M1, the simulator): below this the
# vehicle counts as stationary for door/offload-stop purposes.
STATIONARY_SPEED_KMH = 2.0

# M1's own countdown is the most direct severity signal there is; below
# this many minutes, nothing else needs to be weighed.
CRITICAL_COUNTDOWN_MIN = 15.0

# Shelf life already consumed at or above this floor means there's little
# room left to absorb anything further, regardless of how small the
# current deviation looks in isolation.
STABILITY_BUDGET_CRITICAL_PCT = 90.0

_ACTION_FOR_M2_CAUSE: dict[FaultCause, PrescribedAction] = {
    FaultCause.bearing_wear: PrescribedAction.schedule_service,
    FaultCause.refrigerant_loss: PrescribedAction.schedule_service,
    FaultCause.fan_failure: PrescribedAction.inspect_fan,
    FaultCause.voltage_sag: PrescribedAction.check_electrical,
    FaultCause.unit_off: PrescribedAction.restart_unit,
}


@dataclass
class Diagnosis:
    cause: FaultCause | None
    severity: Severity | None
    evidence: dict[str, float] = field(default_factory=dict)
    prescribed_action: PrescribedAction | None = None
    suppressed: bool = False
    suppression_reason: str | None = None
    confidence: float = 0.0


def _cargo_temps(packet: TelemetryPacket) -> list[float]:
    return [c.t_c for c in packet.cargo if c.pos != ProbePosition.ambient_external]


def _worst_c(packet: TelemetryPacket) -> float:
    return max(_cargo_temps(packet))


def _coldest_c(packet: TelemetryPacket) -> float:
    return min(_cargo_temps(packet))


def _current_door_open_duration_min(
    packet: TelemetryPacket, history: Sequence[TelemetryPacket]
) -> float:
    """Minutes the door has been continuously open in *this* event.

    Walks `history` backward while door.open stays true and door.events
    stays the same value as the current packet's (events increments only on
    a fresh open, so a matching value is how "still the same event" is
    recognised without fusion needing to track it itself).
    """
    if not packet.door.open:
        return 0.0
    start_ts = packet.ts
    for prior in reversed(history):
        if not prior.door.open or prior.door.events != packet.door.events:
            break
        start_ts = prior.ts
    return (packet.ts - start_ts).total_seconds() / 60.0


def _severity_from_signals(
    packet: TelemetryPacket,
    m1: ForecastResult,
    spec: ProfileSpec | None,
    m3: BudgetResult | None,
) -> Severity:
    """Cargo distance to band, M1's countdown, mission profile tolerance
    (via band width -- a tight band uses up its margin faster for the same
    absolute drift), ambient heat (how much worse this is likely to get),
    and M3's stability budget already consumed, when available (a fresh
    excursion on a shipment with little margin left can't be waved off as
    watch just because *this* deviation alone looks small). Does not use
    "remaining journey time" -- see module docstring.
    """
    if m3 is not None and m3.pct_consumed >= STABILITY_BUDGET_CRITICAL_PCT:
        return Severity.critical

    if m1.minutes_to_breach is not None:
        if m1.minutes_to_breach <= CRITICAL_COUNTDOWN_MIN:
            return Severity.critical
        return Severity.warning

    band = packet.band
    if band is None or band.max_c <= band.min_c:
        return Severity.warning

    band_width = band.max_c - band.min_c
    if m1.breach_bound == "lower":
        distance_frac = (_coldest_c(packet) - band.min_c) / band_width
    else:
        distance_frac = (band.max_c - _worst_c(packet)) / band_width
    distance_frac = max(0.0, min(1.0, distance_frac))

    # Hot ambient with real margin left still nudges watch up to warning:
    # the trend has more room to accelerate than the same margin would in
    # mild weather.
    hot_ambient = spec is not None and packet.ambient_c > spec.max_c + 10.0

    if distance_frac <= 0.15:
        return Severity.critical
    if distance_frac <= 0.5 or hot_ambient:
        return Severity.warning
    return Severity.watch


def _base_evidence(
    packet: TelemetryPacket, m1: ForecastResult, m2: ElectricalHealthResult
) -> dict[str, float]:
    evidence: dict[str, float] = {
        "worst_cargo_c": round(_worst_c(packet), 2),
        "coldest_cargo_c": round(_coldest_c(packet), 2),
        "ambient_c": packet.ambient_c,
        "speed_kmh": packet.gnss.speed_kmh,
    }
    if m1.minutes_to_breach is not None:
        evidence["predicted_breach_min"] = round(m1.minutes_to_breach, 1)
    evidence.update(m2.evidence)
    return evidence


def fuse(
    packet: TelemetryPacket,
    m1: ForecastResult,
    m2: ElectricalHealthResult,
    m3: BudgetResult | None,
    history: Sequence[TelemetryPacket],
) -> Diagnosis:
    spec = get_profile(packet.mission_profile) if packet.mission_profile is not None else None
    band = packet.band
    temp_in_band = (
        band is not None and band.min_c <= _coldest_c(packet) and _worst_c(packet) <= band.max_c
    )
    drifting = (m1.minutes_to_breach is not None) or not temp_in_band

    moving = packet.gnss.speed_kmh > STATIONARY_SPEED_KMH
    door_open = packet.door.open
    light_detected = packet.light_lux > LIGHT_DETECTED_LUX_THRESHOLD

    evidence = _base_evidence(packet, m1, m2)

    # Overcooling is its own safety-critical failure mode, disambiguated by
    # direction alone -- checked before anything else so it can never be
    # suppressed or downgraded by door/electrical state.
    if m1.breach_bound == "lower":
        severity = _severity_from_signals(packet, m1, spec, m3)
        if spec is not None and spec.freeze_alarm and severity == Severity.watch:
            severity = Severity.warning
        return Diagnosis(
            cause=FaultCause.freeze_risk,
            severity=severity,
            evidence=evidence,
            prescribed_action=PrescribedAction.raise_within_band,
            suppressed=False,
            suppression_reason=None,
            confidence=0.8,
        )

    # unit_off is a verified fault, not an inferred one -- compressor,
    # condenser fan and evaporator fan all read zero simultaneously (M2's
    # own disambiguation from a lone fan_failure). That's already
    # unambiguous the instant it's true; it does not need to wait for
    # "drifting" to also become true before treating it as critical, which
    # is exactly the "nominal -> critical (hard fault)" transition the
    # alert engine's state machine expects to see, not a few minutes of
    # "warning" while the thermal side catches up.
    if m2.cause == FaultCause.unit_off:
        return Diagnosis(
            cause=FaultCause.unit_off,
            severity=Severity.critical,
            evidence=evidence,
            prescribed_action=PrescribedAction.restart_unit,
            suppressed=False,
            suppression_reason=None,
            confidence=0.95,
        )

    # Door open while moving: no grace period, no suppression -- this is
    # dangerous the instant it's true, independent of how long it's been
    # open or what the temperature is doing.
    if door_open and moving:
        return Diagnosis(
            cause=FaultCause.door_unsecured,
            severity=Severity.critical,
            evidence=evidence,
            prescribed_action=PrescribedAction.secure_door,
            suppressed=False,
            suppression_reason=None,
            confidence=0.95,
        )

    # Door open, stationary: a routine offload stop, corroborated by the
    # light sensor -- a reed switch alone can be taped over, but not
    # simultaneously with the light sensor and the thermal step, which is
    # exactly why this only suppresses when both agree (PROJECT.md's
    # anti-spoofing rationale for carrying three door signals).
    if door_open and not moving:
        dwell_min = _current_door_open_duration_min(packet, history)
        dwell_limit = spec.door_dwell_limit_min if spec is not None else 10.0
        door_evidence = {**evidence, "door_open_min": round(dwell_min, 1)}

        if light_detected and dwell_min <= dwell_limit:
            return Diagnosis(
                cause=FaultCause.offload_stop,
                severity=None,
                evidence=door_evidence,
                prescribed_action=None,
                suppressed=True,
                suppression_reason=(
                    f"door open {dwell_min:.0f} min, within the "
                    f"{dwell_limit:.0f}-min offload dwell limit"
                ),
                confidence=0.9,
            )

        # Past the dwell limit, or open without the light sensor
        # corroborating it (sensor disagreement -- treat as unsecured
        # rather than trusting a single signal): never just "watch."
        severity = _severity_from_signals(packet, m1, spec, m3)
        if severity == Severity.watch:
            severity = Severity.warning
        return Diagnosis(
            cause=FaultCause.door_unsecured,
            severity=severity,
            evidence=door_evidence,
            prescribed_action=PrescribedAction.close_door,
            suppressed=False,
            suppression_reason=None,
            confidence=0.85 if light_detected else 0.6,
        )

    # Door is closed from here on -- the quadrant proper.
    current_abnormal = m2.cause is not None

    if not current_abnormal and not drifting:
        return Diagnosis(
            cause=None,
            severity=None,
            evidence=evidence,
            prescribed_action=None,
            suppressed=False,
            suppression_reason=None,
            confidence=0.95,
        )

    if current_abnormal and not drifting:
        # The product's core claim: M2 alone, no near-term breach, no wait
        # on M1 (which caps forecasts at 40min and has nothing to say about
        # a fault this early). Never critical -- cargo is genuinely fine
        # right now.
        assert m2.cause is not None
        return Diagnosis(
            cause=m2.cause,
            severity=Severity.warning,
            evidence=evidence,
            prescribed_action=PrescribedAction.schedule_service,
            suppressed=False,
            suppression_reason=None,
            confidence=0.75,
        )

    if current_abnormal and drifting:
        # unit_off never reaches here -- it's a hard fault, handled above
        # regardless of drift state.
        assert m2.cause is not None
        severity = _severity_from_signals(packet, m1, spec, m3)
        action = _ACTION_FOR_M2_CAUSE.get(m2.cause, PrescribedAction.check_electrical)
        return Diagnosis(
            cause=m2.cause,
            severity=severity,
            evidence=evidence,
            prescribed_action=action,
            suppressed=False,
            suppression_reason=None,
            confidence=0.85,
        )

    # current normal, drifting, door closed: neither electrical state nor
    # the door explains a real thermal drift -- the compartment itself
    # (seal, load, insulation) is the remaining candidate. Diagnosis by
    # elimination, not a direct signal -- lower confidence reflects that.
    return Diagnosis(
        cause=FaultCause.seal_failure,
        severity=_severity_from_signals(packet, m1, spec, m3),
        evidence=evidence,
        prescribed_action=PrescribedAction.inspect_seals,
        suppressed=False,
        suppression_reason=None,
        confidence=0.55,
    )
