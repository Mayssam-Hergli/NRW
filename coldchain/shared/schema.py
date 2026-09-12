from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.enums import (
    AlertState,
    CompressorState,
    DriverCause,
    FaultCause,
    GnssFix,
    MissionProfile,
    Outcome,
    PrescribedAction,
    ProbePosition,
    Severity,
)
from shared.profiles import get_profile

SCHEMA_VERSION = "1.0"

TELEMETRY_TOPIC = "fleet/{tenant}/vehicle/{device_id}/telemetry"
ALERT_TOPIC = "fleet/{tenant}/vehicle/{device_id}/alert"
CONFIG_TOPIC = "fleet/{tenant}/vehicle/{device_id}/config"


def topic_for(template: str, tenant: str, device_id: str) -> str:
    return template.format(tenant=tenant, device_id=device_id)


class Band(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_c: float = Field(description="Lower bound of the acceptable temperature band, in C.")
    max_c: float = Field(description="Upper bound of the acceptable temperature band, in C.")

    @model_validator(mode="after")
    def _check_band(self) -> Band:
        if self.min_c >= self.max_c:
            raise ValueError("min_c must be less than max_c")
        return self


class Gnss(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90, description="Latitude in decimal degrees.")
    lon: float = Field(ge=-180, le=180, description="Longitude in decimal degrees.")
    speed_kmh: float = Field(ge=0, description="Ground speed in km/h.")
    fix: GnssFix = Field(description="GNSS fix quality.")


class CargoReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str = Field(description="Unique identifier of the probe within the packet.")
    pos: ProbePosition = Field(description="Physical mounting position of the probe.")
    t_c: float = Field(description="Cargo temperature in Celsius.")
    rh: float | None = Field(
        default=None, ge=0, le=100, description="Relative humidity percent, if sensed."
    )


class DoorState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open: bool = Field(description="Whether the cargo door is currently open.")
    events: int = Field(
        ge=0, description="Count of door open/close events since the last uplink."
    )


class Motion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peak_g: float = Field(ge=0, description="Peak shock magnitude observed, in g.")
    shock_events: int = Field(ge=0, description="Count of shock events above threshold.")
    vib_rms: float = Field(ge=0, description="RMS vibration level.")


class Channel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    i_rms: float = Field(ge=0, description="RMS current draw of the channel, in amps.")
    inrush_peak: float | None = Field(
        default=None, ge=0, description="Peak inrush current, in amps."
    )
    duty_pct: float | None = Field(
        default=None, ge=0, le=100, description="Duty cycle percent over the sample window."
    )


class Power(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v_bus: float = Field(ge=0, description="Refrigeration unit bus voltage.")
    compressor: Channel = Field(description="Compressor current channel.")
    cond_fan: Channel = Field(description="Condenser fan current channel.")
    evap_fan: Channel = Field(description="Evaporator fan current channel.")
    state: CompressorState = Field(description="Current compressor state.")


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batt_v: float = Field(ge=0, description="Gateway backup battery voltage.")
    rssi: int = Field(description="Cellular signal strength, in dBm.")
    buffer_pct: float = Field(ge=0, le=100, description="Percent of flash offline-buffer in use.")
    gnss_fix: GnssFix = Field(
        description="Most recent GNSS fix quality known to the gateway."
    )


class TelemetryPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(description="Unique identifier of the gateway device.")
    shipment_id: str | None = Field(
        default=None, description="Identifier of the active shipment, if any."
    )
    mission_profile: MissionProfile | None = Field(
        default=None, description="Mission profile governing this shipment."
    )
    band: Band | None = Field(
        default=None, description="Acceptable temperature band for this shipment."
    )
    ts: datetime = Field(description="Timestamp of this reading, timezone-aware.")
    seq: int = Field(ge=0, description="Monotonically increasing sequence number per device.")
    buffered: bool = Field(
        default=False, description="Whether this packet was replayed from offline flash buffer."
    )
    gnss: Gnss = Field(description="Vehicle position and speed.")
    cargo: list[CargoReading] = Field(
        min_length=1, max_length=12, description="Cargo temperature probe readings."
    )
    ambient_c: float = Field(description="Ambient temperature outside the cargo area, in C.")
    door: DoorState = Field(description="Cargo door state.")
    light_lux: float = Field(ge=0, description="Light exposure at the cargo door, in lux.")
    motion: Motion = Field(description="Shock and vibration summary.")
    power: Power = Field(description="Refrigeration unit electrical summary.")
    health: Health = Field(description="Gateway device health summary.")
    sig: str | None = Field(
        default=None, description="Hex-encoded signature over the packet payload."
    )

    @model_validator(mode="after")
    def _check_ts_aware(self) -> TelemetryPacket:
        if self.ts.tzinfo is None:
            raise ValueError("ts must be timezone-aware")
        return self

    @model_validator(mode="after")
    def _check_shipment_requires_profile_link(self) -> TelemetryPacket:
        if self.mission_profile is not None and self.shipment_id is None:
            raise ValueError("shipment_id is required when mission_profile is set")
        return self

    @model_validator(mode="after")
    def _check_cargo_tags_unique(self) -> TelemetryPacket:
        tags = [c.tag for c in self.cargo]
        if len(tags) != len(set(tags)):
            raise ValueError("cargo tags must be unique")
        return self

    @model_validator(mode="after")
    def _check_single_ambient_external(self) -> TelemetryPacket:
        n = sum(1 for c in self.cargo if c.pos == ProbePosition.ambient_external)
        if n > 1:
            raise ValueError("at most one cargo entry may have pos == ambient_external")
        return self


class AlertRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: str = Field(description="Unique identifier of the alert.")
    device_id: str = Field(description="Device that raised the alert.")
    shipment_id: str | None = Field(
        default=None, description="Shipment associated with the alert, if any."
    )
    issued_ts: datetime = Field(description="Timestamp the alert was first issued.")
    tier: int = Field(
        ge=1, le=3, description="Escalation tier, 1 (local/driver) to 3 (dispatcher escalation)."
    )
    state: AlertState = Field(description="Current lifecycle state of the alert.")
    severity: Severity = Field(description="Severity classification.")
    cause: FaultCause = Field(description="Diagnosed root cause.")
    evidence: dict[str, float] = Field(
        description="Named signal values supporting the diagnosis."
    )
    predicted_breach_min: float | None = Field(
        default=None, description="Predicted minutes until band breach, if applicable."
    )
    prescribed_action: PrescribedAction = Field(
        description="Recommended action for the driver or dispatcher."
    )
    message: str = Field(description="Human-readable alert message.")
    ack_ts: datetime | None = Field(
        default=None, description="Timestamp the alert was acknowledged."
    )
    driver_cause: DriverCause | None = Field(
        default=None, description="Cause reported by the driver, if acknowledged."
    )
    action_taken: str | None = Field(
        default=None, description="Free-text description of the action taken."
    )
    outcome: Outcome = Field(
        default=Outcome.pending, description="Resolution outcome of the alert."
    )
    delivered_offline: bool = Field(
        default=False, description="Whether the alert was raised while the device was offline."
    )
    escalated_ts: datetime | None = Field(
        default=None, description="Timestamp the alert was escalated, if any."
    )
    resolved_ts: datetime | None = Field(
        default=None, description="Timestamp the alert was resolved, if any."
    )

    @model_validator(mode="after")
    def _check_ack_after_issued(self) -> AlertRecord:
        if self.ack_ts is not None and self.ack_ts < self.issued_ts:
            raise ValueError("ack_ts must not be before issued_ts")
        return self

    @model_validator(mode="after")
    def _check_ack_required_for_state(self) -> AlertRecord:
        if self.state in (AlertState.acknowledged, AlertState.resolved) and self.ack_ts is None:
            raise ValueError("ack_ts is required when state is acknowledged or resolved")
        return self

    @model_validator(mode="after")
    def _check_outcome_requires_ack(self) -> AlertRecord:
        if self.outcome != Outcome.pending and self.ack_ts is None:
            raise ValueError("outcome cannot leave pending without ack_ts")
        return self


class ConfigDownlink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(description="Device this configuration applies to.")
    issued_ts: datetime = Field(description="Timestamp this configuration was issued.")
    sample_interval_s: int = Field(ge=1, le=60, description="High-rate sensing interval, in s.")
    uplink_interval_s: int = Field(
        ge=15, le=600, description="Feature packet uplink interval, in seconds."
    )
    capture_waveform: bool = Field(
        default=False, description="Whether to capture raw waveform snippets for diagnostics."
    )
    thresholds: dict[str, float] = Field(
        description="Named threshold overrides for local alerting."
    )

    @model_validator(mode="after")
    def _check_uplink_not_faster_than_sample(self) -> ConfigDownlink:
        if self.uplink_interval_s < self.sample_interval_s:
            raise ValueError("uplink_interval_s must be >= sample_interval_s")
        return self


def example_packet() -> TelemetryPacket:
    profile = get_profile(MissionProfile.pharma_refrigerated)
    return TelemetryPacket(
        device_id="ESP32-TN-0042",
        shipment_id="SHIP-20260912-07",
        mission_profile=MissionProfile.pharma_refrigerated,
        band=Band(min_c=profile.min_c, max_c=profile.max_c),
        ts=datetime(2026, 9, 12, 9, 30, 0, tzinfo=UTC),
        seq=118,
        buffered=False,
        gnss=Gnss(lat=36.8065, lon=10.1815, speed_kmh=72.5, fix=GnssFix.D3),
        cargo=[
            CargoReading(tag="P1", pos=ProbePosition.front, t_c=4.2, rh=45.0),
            CargoReading(tag="P2", pos=ProbePosition.rear_door, t_c=5.1),
            CargoReading(tag="P3", pos=ProbePosition.top, t_c=4.6),
        ],
        ambient_c=27.3,
        door=DoorState(open=False, events=2),
        light_lux=0.0,
        motion=Motion(peak_g=0.8, shock_events=0, vib_rms=0.05),
        power=Power(
            v_bus=27.8,
            compressor=Channel(i_rms=4.2, inrush_peak=9.1, duty_pct=62.0),
            cond_fan=Channel(i_rms=0.9),
            evap_fan=Channel(i_rms=0.7),
            state=CompressorState.RUN,
        ),
        health=Health(batt_v=12.6, rssi=-71, buffer_pct=0.0, gnss_fix=GnssFix.D3),
        sig=None,
    )
