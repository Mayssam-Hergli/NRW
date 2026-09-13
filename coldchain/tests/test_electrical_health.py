from __future__ import annotations

from datetime import UTC, datetime, timedelta

from models.electrical_health import ElectricalHealthMonitor
from shared.enums import CompressorState, FaultCause, GnssFix, ProbePosition
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
from simulator.scenarios import NominalScenario, RefrigerantLossScenario

_BASE_TS = datetime(2026, 1, 1, tzinfo=UTC)
_BAND = Band(min_c=2.0, max_c=8.0)


def _packet(
    *,
    seq: int,
    t_min: float,
    i_compressor: float,
    i_cond_fan: float,
    i_evap_fan: float,
    state: CompressorState,
) -> TelemetryPacket:
    """A minimal, schema-valid packet with hand-picked power channel
    readings, for testing the health monitor's decision logic directly
    against exact, deterministic channel states rather than relying on
    catching the underlying physics sim at a lucky instant.
    """
    return TelemetryPacket(
        device_id="TEST-GW",
        shipment_id="SHIP-TEST",
        mission_profile=None,
        band=_BAND,
        ts=_BASE_TS + timedelta(minutes=t_min),
        seq=seq,
        gnss=Gnss(lat=34.74, lon=10.76, speed_kmh=80.0, fix=GnssFix.D3),
        cargo=[CargoReading(tag="P1", pos=ProbePosition.front, t_c=5.0)],
        ambient_c=30.0,
        door=DoorState(open=False, events=0),
        light_lux=0.0,
        motion=Motion(peak_g=0.0, shock_events=0, vib_rms=0.0),
        power=Power(
            v_bus=24.0,
            compressor=Channel(i_rms=i_compressor, duty_pct=30.0),
            cond_fan=Channel(i_rms=i_cond_fan),
            evap_fan=Channel(i_rms=i_evap_fan),
            state=state,
        ),
        health=Health(batt_v=12.6, rssi=-70, buffer_pct=0.0, gnss_fix=GnssFix.D3),
    )


def test_zero_anomalies_on_nominal() -> None:
    scenario = NominalScenario()
    monitor = ElectricalHealthMonitor(dt_min=1.0)
    elec = ElectricalSim(scenario.profile)

    anomalies = []
    for packet in scenario.run(dt_s=60.0):
        expected = elec.expected_duty_pct(packet.ambient_c, packet.gnss.speed_kmh)
        result = monitor.update(packet, expected)
        if result.cause is not None:
            anomalies.append((packet.seq, result.cause))

    assert anomalies == []


def test_refrigerant_loss_detected_before_thermal_breach() -> None:
    scenario = RefrigerantLossScenario()
    # The scenario's own default_duration_min (48h) never actually breaches
    # band at the 0.3 capacity floor; run long enough that it does, so
    # "detected before breach" is a real assertion, not a vacuous one.
    duration_min = 6000.0
    gt = scenario.ground_truth(duration_min=duration_min)
    breach_t = gt["expected_thermal_breach_min"]
    assert breach_t is not None, "expected a real breach at this duration"

    monitor = ElectricalHealthMonitor(dt_min=1.0)
    elec = ElectricalSim(scenario.profile)

    detect_t: float | None = None
    t_min = 0.0
    for packet in scenario.run(duration_min=duration_min, dt_s=60.0):
        expected = elec.expected_duty_pct(packet.ambient_c, packet.gnss.speed_kmh)
        result = monitor.update(packet, expected)
        if detect_t is None:
            if result.cause == FaultCause.refrigerant_loss:
                detect_t = t_min
            elif result.cause is not None:
                raise AssertionError(f"unexpected cause before refrigerant_loss: {result.cause}")
        t_min += 1.0

    assert detect_t is not None
    if breach_t is not None:
        assert detect_t < breach_t


def test_isolated_evap_fan_failure_is_fan_failure_not_unit_off() -> None:
    monitor = ElectricalHealthMonitor(dt_min=1.0)
    result = None
    # Compressor and condenser fan keep drawing current the whole time;
    # only the evaporator fan is dead. Feed enough steps to clear the
    # unit_off sustain window and confirm it still isn't misread as one.
    for i in range(6):
        packet = _packet(
            seq=i,
            t_min=i,
            i_compressor=4.4,
            i_cond_fan=0.9,
            i_evap_fan=0.0,
            state=CompressorState.RUN,
        )
        result = monitor.update(packet, expected_duty_pct=30.0)

    assert result is not None
    assert result.cause == FaultCause.fan_failure
    assert result.cause != FaultCause.unit_off
    assert result.evidence["evap_fan_i"] == 0.0
    assert result.evidence["cond_fan_i"] == 0.9


def test_isolated_cond_fan_failure_is_fan_failure() -> None:
    monitor = ElectricalHealthMonitor(dt_min=1.0)
    packet = _packet(
        seq=0, t_min=0, i_compressor=4.4, i_cond_fan=0.0, i_evap_fan=0.7, state=CompressorState.RUN
    )
    result = monitor.update(packet, expected_duty_pct=30.0)

    assert result.cause == FaultCause.fan_failure
    assert result.evidence["cond_fan_i"] == 0.0
    assert result.evidence["evap_fan_i"] == 0.7


def test_all_channels_zero_is_genuinely_unit_off() -> None:
    monitor = ElectricalHealthMonitor(dt_min=1.0)
    result = None
    for i in range(6):
        packet = _packet(
            seq=i,
            t_min=i,
            i_compressor=0.0,
            i_cond_fan=0.0,
            i_evap_fan=0.0,
            state=CompressorState.OFF,
        )
        result = monitor.update(packet, expected_duty_pct=0.0)

    assert result is not None
    assert result.cause == FaultCause.unit_off


def test_compressor_off_between_normal_cycles_raises_no_fault() -> None:
    # A healthy compressor is off most of the time. If that alone ever
    # reads as a fault, "nominal" would alarm constantly.
    monitor = ElectricalHealthMonitor(dt_min=1.0)
    for i in range(10):
        packet = _packet(
            seq=i,
            t_min=i,
            i_compressor=0.0,
            i_cond_fan=0.0,
            i_evap_fan=0.7,
            state=CompressorState.OFF,
        )
        result = monitor.update(packet, expected_duty_pct=0.0)
        assert result.cause is None
