from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta

from models.electrical_health import ElectricalHealthMonitor
from models.fusion import Diagnosis, fuse
from models.m1_thermal import M1ThermalForecast
from shared.enums import (
    CompressorState,
    FaultCause,
    GnssFix,
    PrescribedAction,
    ProbePosition,
    Severity,
)
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
from simulator.electrical import ElectricalSim
from simulator.scenarios import (
    CompressorFailureScenario,
    DoorOpenScenario,
    FreezeRiskScenario,
    NominalScenario,
    RefrigerantLossScenario,
)

HISTORY_LIMIT = 30


def _run_fusion_over_scenario(
    scenario, duration_min: float | None = None, dt_s: float = 60.0
) -> list[tuple[TelemetryPacket, Diagnosis]]:
    m1 = M1ThermalForecast()
    m2 = ElectricalHealthMonitor(dt_min=dt_s / 60.0)
    elec = ElectricalSim(scenario.profile)
    history: deque[TelemetryPacket] = deque(maxlen=HISTORY_LIMIT)

    results = []
    for packet in scenario.run(duration_min=duration_min, dt_s=dt_s):
        r1 = m1.update(packet)
        expected_duty = elec.expected_duty_pct(packet.ambient_c, packet.gnss.speed_kmh)
        r2 = m2.update(packet, expected_duty)
        diagnosis = fuse(packet, r1, r2, None, list(history))
        results.append((packet, diagnosis))
        history.append(packet)
    return results


# --- synthetic packet builder, for cases none of the six scenarios cover --


def _packet(
    *,
    t_c: float = 5.0,
    band: tuple[float, float] = (2.0, 8.0),
    door_open: bool = False,
    door_events: int = 0,
    light_lux: float = 0.0,
    speed_kmh: float = 0.0,
    ambient_c: float = 30.0,
    compressor_i: float = 4.0,
    cond_fan_i: float = 0.9,
    evap_fan_i: float = 0.7,
    compressor_state: CompressorState = CompressorState.RUN,
    mission_profile: MissionProfile = MissionProfile.pharma_refrigerated,
    seq: int = 0,
    ts: datetime | None = None,
) -> TelemetryPacket:
    return TelemetryPacket(
        device_id="TEST-GW",
        shipment_id="SHIP-TEST",
        mission_profile=mission_profile,
        band=Band(min_c=band[0], max_c=band[1]),
        ts=ts or datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=seq),
        seq=seq,
        buffered=False,
        gnss=Gnss(lat=36.8, lon=10.18, speed_kmh=speed_kmh, fix=GnssFix.D3),
        cargo=[CargoReading(tag="P1", pos=ProbePosition.bottom, t_c=t_c)],
        ambient_c=ambient_c,
        door=DoorState(open=door_open, events=door_events),
        light_lux=light_lux,
        motion=Motion(peak_g=0.1, shock_events=0, vib_rms=0.01),
        power=Power(
            v_bus=24.0,
            compressor=Channel(i_rms=compressor_i, inrush_peak=None, duty_pct=50.0),
            cond_fan=Channel(i_rms=cond_fan_i),
            evap_fan=Channel(i_rms=evap_fan_i),
            state=compressor_state,
        ),
        health=Health(batt_v=12.6, rssi=-70, buffer_pct=0.0, gnss_fix=GnssFix.D3),
        sig=None,
    )


def _forecast_result(minutes_to_breach=None, breach_bound=None, trend=0.0):
    from models.m1_thermal import ForecastResult

    return ForecastResult(
        minutes_to_breach=minutes_to_breach,
        breach_bound=breach_bound,
        tau_estimate_min=120.0,
        tau_confidence=0.9,
        per_probe={},
        trend_c_per_min=trend,
    )


def _electrical_result(cause=None, evidence=None):
    from models.electrical_health import ElectricalHealthResult

    return ElectricalHealthResult(cause=cause, evidence=evidence or {})


# --- healthy / suppression -------------------------------------------------


def test_nominal_produces_no_diagnosis_at_all() -> None:
    results = _run_fusion_over_scenario(NominalScenario())
    non_healthy = [(p.seq, d) for p, d in results if d.cause is not None]
    assert non_healthy == []


def test_door_open_offload_stop_is_suppressed_within_dwell_limit() -> None:
    results = _run_fusion_over_scenario(DoorOpenScenario())
    spec = get_profile(DoorOpenScenario.profile)
    door_results = [(p, d) for p, d in results if p.door.open]
    assert door_results, "expected some door-open packets"

    first_p, first_d = door_results[0]
    assert first_d.suppressed is True
    assert first_d.cause == FaultCause.offload_stop
    assert first_d.severity is None
    assert first_d.suppression_reason is not None

    # No packet within the dwell limit should ever produce a live alert.
    for p, d in door_results:
        dwell_so_far = sum(
            1 for pp, _ in door_results if pp.door.events == p.door.events and pp.seq <= p.seq
        )
        if dwell_so_far <= spec.door_dwell_limit_min:
            assert d.suppressed or d.cause is None


def test_door_open_beyond_dwell_limit_becomes_door_unsecured() -> None:
    # DOOR_OPEN_DURATION_MIN (18) exceeds pharma_refrigerated's dwell limit
    # (10), so the tail of the door-open window should escalate.
    results = _run_fusion_over_scenario(DoorOpenScenario())
    door_results = [(p, d) for p, d in results if p.door.open]
    last_p, last_d = door_results[-1]
    assert last_d.suppressed is False
    assert last_d.cause == FaultCause.door_unsecured
    assert last_d.severity in (Severity.warning, Severity.critical)
    assert last_d.prescribed_action == PrescribedAction.close_door


# --- door open while moving: immediately critical, no grace ---------------


def test_door_open_while_moving_is_immediately_critical() -> None:
    p = _packet(door_open=True, door_events=1, speed_kmh=60.0, light_lux=0.0)
    diag = fuse(p, _forecast_result(), _electrical_result(), None, [])
    assert diag.cause == FaultCause.door_unsecured
    assert diag.severity == Severity.critical
    assert diag.suppressed is False
    assert diag.prescribed_action == PrescribedAction.secure_door


def test_door_open_while_moving_is_critical_even_at_the_very_first_instant() -> None:
    # No dwell grace at all, unlike the stationary case -- true even with
    # empty history (the door just opened this instant).
    p = _packet(door_open=True, door_events=1, speed_kmh=45.0, light_lux=20000.0)
    diag = fuse(p, _forecast_result(), _electrical_result(), None, [])
    assert diag.severity == Severity.critical


# --- electrical causes: predictive window vs active failure ---------------


def test_refrigerant_loss_predictive_window_before_any_breach() -> None:
    results = _run_fusion_over_scenario(RefrigerantLossScenario(), duration_min=6000.0)
    predictive = [
        (p, d)
        for p, d in results
        if d.cause == FaultCause.refrigerant_loss and d.severity == Severity.warning
    ]
    assert predictive, "expected refrigerant_loss to be flagged before any breach"
    first_p, first_d = predictive[0]
    # Money-shot quadrant: fires without M1 having a countdown yet.
    assert "predicted_breach_min" not in first_d.evidence
    assert first_d.prescribed_action == PrescribedAction.schedule_service
    assert first_d.suppressed is False


def test_refrigerant_loss_never_critical_in_the_predictive_window() -> None:
    # "In band" (raw reading) alone isn't the right test -- fusion's own
    # notion of the predictive-window quadrant is specifically (temp
    # actually within [min_c, max_c] right now) AND (M1 has no countdown).
    # A packet can be missing a countdown for a different reason too (e.g.
    # so far past the band for so long that M1's own trend detector no
    # longer sees a rising slope to report) -- that's not the predictive
    # window and critical is legitimate there. Recomputing fusion's own
    # condition directly, rather than using evidence-dict absence as a
    # proxy, is what makes this test actually check the right thing.
    results = _run_fusion_over_scenario(RefrigerantLossScenario(), duration_min=6000.0)
    spec = get_profile(RefrigerantLossScenario.profile)
    checked_any = False
    for p, d in results:
        if d.cause != FaultCause.refrigerant_loss:
            continue
        worst = max(c.t_c for c in p.cargo)
        coldest = min(c.t_c for c in p.cargo)
        temp_in_band = spec.min_c <= coldest and worst <= spec.max_c
        no_countdown = "predicted_breach_min" not in d.evidence
        if temp_in_band and no_countdown:
            checked_any = True
            assert d.severity == Severity.warning
    assert checked_any, "expected at least one packet in the predictive window"


def test_fan_failure_stays_fan_failure_not_unit_off() -> None:
    # M2 already disambiguates this; fusion must not reinterpret it.
    p = _packet(t_c=7.5, door_open=False, evap_fan_i=0.0, cond_fan_i=0.0, compressor_i=4.0)
    m2 = _electrical_result(cause=FaultCause.fan_failure, evidence={"cond_fan_i": 0.0})
    diag = fuse(p, _forecast_result(minutes_to_breach=20.0, breach_bound="upper"), m2, None, [])
    assert diag.cause == FaultCause.fan_failure
    assert diag.cause != FaultCause.unit_off
    assert diag.prescribed_action == PrescribedAction.inspect_fan


def test_unit_off_with_drift_is_critical() -> None:
    p = _packet(t_c=7.8, door_open=False)
    m2 = _electrical_result(cause=FaultCause.unit_off, evidence={"mins": 5.0})
    diag = fuse(p, _forecast_result(minutes_to_breach=8.0, breach_bound="upper"), m2, None, [])
    assert diag.cause == FaultCause.unit_off
    assert diag.severity == Severity.critical
    assert diag.prescribed_action == PrescribedAction.restart_unit


# --- seal failure: temp drifting, current normal, door closed -------------


def test_seal_failure_when_nothing_else_explains_the_drift() -> None:
    p = _packet(t_c=7.6, door_open=False)
    m1 = _forecast_result(minutes_to_breach=25.0, breach_bound="upper")
    diag = fuse(p, m1, _electrical_result(), None, [])
    assert diag.cause == FaultCause.seal_failure
    assert diag.prescribed_action == PrescribedAction.inspect_seals
    assert diag.confidence < 0.7  # diagnosis by elimination, not a direct signal


# --- freeze risk: never suppressed, never "just watch" ---------------------


def test_freeze_risk_on_vaccines_is_never_suppressed_or_watch_only() -> None:
    results = _run_fusion_over_scenario(FreezeRiskScenario())
    spec = get_profile(FreezeRiskScenario.profile)
    assert spec.freeze_alarm is True
    freeze_results = [(p, d) for p, d in results if d.cause == FaultCause.freeze_risk]
    assert freeze_results, "expected freeze_risk to fire on this scenario"
    for _, d in freeze_results:
        assert d.suppressed is False
        assert d.severity in (Severity.warning, Severity.critical)


def test_freeze_risk_even_while_door_closed_and_current_normal() -> None:
    p = _packet(
        t_c=2.8,
        band=(2.0, 8.0),
        mission_profile=MissionProfile.vaccines,
        door_open=False,
    )
    m1 = _forecast_result(minutes_to_breach=10.0, breach_bound="lower")
    diag = fuse(p, m1, _electrical_result(), None, [])
    assert diag.cause == FaultCause.freeze_risk
    assert diag.severity == Severity.critical


# --- the headline test: identical thermal slope, three different stories --


def test_headline_door_open_vs_unit_off_on_comparable_thermal_slopes() -> None:
    """Same thermal signature -- a real, non-trivial upper-bound countdown
    -- resolved completely differently depending on what the other domains
    say: a door left open too long is a warning to close it; verified zero
    current on every channel is a critical restart. Cause, severity, and
    prescribed action must all three differ.
    """
    m1 = _forecast_result(minutes_to_breach=20.0, breach_bound="upper")

    door_packet = _packet(t_c=7.0, door_open=True, door_events=1, speed_kmh=0.0, light_lux=0.0)
    # 15 minutes of prior history on the same door-open event -- past
    # pharma_refrigerated's 10-minute dwell limit, and light_lux=0.0 means
    # the light sensor never corroborated it either.
    history = [
        door_packet.model_copy(
            update={"seq": i, "ts": door_packet.ts - timedelta(minutes=15 - i)}
        )
        for i in range(15)
    ]
    door_diag = fuse(door_packet, m1, _electrical_result(), None, history)

    unit_off_packet = _packet(t_c=7.0, door_open=False)
    unit_off_m2 = _electrical_result(cause=FaultCause.unit_off, evidence={"mins": 5.0})
    unit_off_diag = fuse(unit_off_packet, m1, unit_off_m2, None, [])

    assert door_diag.cause != unit_off_diag.cause
    assert door_diag.severity != unit_off_diag.severity
    assert door_diag.prescribed_action != unit_off_diag.prescribed_action
    assert unit_off_diag.severity == Severity.critical
    assert unit_off_diag.prescribed_action == PrescribedAction.restart_unit
    assert door_diag.prescribed_action == PrescribedAction.close_door


# --- compressor_failure: bearing warning first, then unit_off critical ----


def test_compressor_failure_bearing_warning_then_unit_off_critical() -> None:
    results = _run_fusion_over_scenario(CompressorFailureScenario(), duration_min=260.0)
    bearing_events = [(p.seq, d) for p, d in results if d.cause == FaultCause.bearing_wear]
    unit_off_events = [(p.seq, d) for p, d in results if d.cause == FaultCause.unit_off]

    assert bearing_events, "expected an early bearing_wear warning"
    assert unit_off_events, "expected unit_off once the unit actually stops"
    assert bearing_events[-1][0] < unit_off_events[0][0]
    assert all(d.severity == Severity.warning for _, d in bearing_events)
    assert all(d.severity == Severity.critical for _, d in unit_off_events)


# --- same fault, different severity depending on context ------------------


def test_same_fault_different_severity_under_different_contexts() -> None:
    # "A failed fan is warning on a short run in mild weather and critical
    # on a four-hour leg into Medenine heat with cargo close to the edge"
    # (PROJECT.md) -- same cause, context (how soon the thermal consequence
    # actually lands) decides severity, not the electrical fault alone.
    mild_m1 = _forecast_result(minutes_to_breach=35.0, breach_bound="upper")
    mild_packet = _packet(t_c=5.0, ambient_c=22.0, door_open=False)
    mild_diag = fuse(
        mild_packet, mild_m1, _electrical_result(cause=FaultCause.fan_failure), None, []
    )

    hot_m1 = _forecast_result(minutes_to_breach=8.0, breach_bound="upper")
    hot_packet = _packet(t_c=7.2, ambient_c=42.0, door_open=False)
    hot_diag = fuse(hot_packet, hot_m1, _electrical_result(cause=FaultCause.fan_failure), None, [])

    assert mild_diag.cause == FaultCause.fan_failure == hot_diag.cause
    assert mild_diag.severity == Severity.warning
    assert hot_diag.severity == Severity.critical
