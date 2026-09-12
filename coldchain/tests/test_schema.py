from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from shared.enums import (
    AlertState,
    FaultCause,
    GnssFix,
    MissionProfile,
    Outcome,
    PrescribedAction,
    ProbePosition,
    Severity,
)
from shared.profiles import PROFILES, get_profile
from shared.schema import (
    ALERT_TOPIC,
    AlertRecord,
    Band,
    ConfigDownlink,
    Gnss,
    TelemetryPacket,
    example_packet,
    topic_for,
)
from shared.wire import from_wire, monthly_mb, to_wire, wire_size


def _base_alert_kwargs(**overrides: object) -> dict:
    kwargs = dict(
        alert_id="AL-1",
        device_id="ESP32-TN-0042",
        shipment_id="SHIP-1",
        issued_ts=datetime(2026, 9, 12, 9, 0, 0, tzinfo=UTC),
        tier=1,
        state=AlertState.watch,
        severity=Severity.watch,
        cause=FaultCause.door_unsecured,
        evidence={"door_open_s": 45.0},
        prescribed_action=PrescribedAction.close_door,
        message="Door has been open for 45s.",
    )
    kwargs.update(overrides)
    return kwargs


def test_example_packet_roundtrips_through_json() -> None:
    packet = example_packet()
    restored = TelemetryPacket.model_validate_json(packet.model_dump_json())
    assert restored == packet


def test_naive_ts_rejected() -> None:
    kwargs = example_packet().model_dump(mode="python")
    kwargs["ts"] = datetime(2026, 9, 12, 9, 30, 0)  # naive  # noqa: DTZ001
    with pytest.raises(ValidationError):
        TelemetryPacket.model_validate(kwargs)


def test_inverted_band_rejected() -> None:
    with pytest.raises(ValidationError):
        Band(min_c=8.0, max_c=2.0)


def test_unknown_extra_field_rejected() -> None:
    kwargs = example_packet().model_dump(mode="python")
    kwargs["unexpected_field"] = 1
    with pytest.raises(ValidationError):
        TelemetryPacket.model_validate(kwargs)


def test_duplicate_cargo_tags_rejected() -> None:
    kwargs = example_packet().model_dump(mode="python")
    kwargs["cargo"][1]["tag"] = kwargs["cargo"][0]["tag"]
    with pytest.raises(ValidationError):
        TelemetryPacket.model_validate(kwargs)


def test_two_ambient_external_probes_rejected() -> None:
    kwargs = example_packet().model_dump(mode="python")
    kwargs["cargo"][0]["pos"] = ProbePosition.ambient_external
    kwargs["cargo"][1]["pos"] = ProbePosition.ambient_external
    with pytest.raises(ValidationError):
        TelemetryPacket.model_validate(kwargs)


def test_latitude_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        Gnss(lat=91.0, lon=10.0, speed_kmh=0.0, fix=GnssFix.D3)


def test_mission_profile_without_shipment_id_rejected() -> None:
    kwargs = example_packet().model_dump(mode="python")
    kwargs["shipment_id"] = None
    with pytest.raises(ValidationError):
        TelemetryPacket.model_validate(kwargs)


def test_alert_acknowledged_without_ack_ts_rejected() -> None:
    with pytest.raises(ValidationError):
        AlertRecord(**_base_alert_kwargs(state=AlertState.acknowledged))


def test_alert_outcome_set_without_ack_ts_rejected() -> None:
    with pytest.raises(ValidationError):
        AlertRecord(**_base_alert_kwargs(outcome=Outcome.recovered))


def test_alert_ack_ts_before_issued_ts_rejected() -> None:
    issued_ts = datetime(2026, 9, 12, 9, 0, 0, tzinfo=UTC)
    with pytest.raises(ValidationError):
        AlertRecord(
            **_base_alert_kwargs(
                issued_ts=issued_ts,
                state=AlertState.acknowledged,
                ack_ts=issued_ts - timedelta(seconds=1),
            )
        )


def test_valid_acknowledged_alert_accepted() -> None:
    issued_ts = datetime(2026, 9, 12, 9, 0, 0, tzinfo=UTC)
    alert = AlertRecord(
        **_base_alert_kwargs(
            issued_ts=issued_ts,
            state=AlertState.acknowledged,
            ack_ts=issued_ts + timedelta(seconds=30),
        )
    )
    assert alert.state == AlertState.acknowledged


def test_config_downlink_uplink_faster_than_sample_rejected() -> None:
    with pytest.raises(ValidationError):
        ConfigDownlink(
            device_id="ESP32-TN-0042",
            issued_ts=datetime(2026, 9, 12, 9, 0, 0, tzinfo=UTC),
            sample_interval_s=30,
            uplink_interval_s=15,
            thresholds={},
        )


def test_vaccines_profile_has_freeze_alarm_true() -> None:
    assert get_profile(MissionProfile.vaccines).freeze_alarm is True


def test_pharma_refrigerated_profile_has_freeze_alarm_false() -> None:
    assert get_profile(MissionProfile.pharma_refrigerated).freeze_alarm is False


def test_all_profiles_present() -> None:
    assert set(PROFILES) == set(MissionProfile)


def test_topic_helper_formats_correctly() -> None:
    assert (
        topic_for(ALERT_TOPIC, tenant="acme", device_id="ESP32-TN-0042")
        == "fleet/acme/vehicle/ESP32-TN-0042/alert"
    )


def test_wire_roundtrips_exactly() -> None:
    packet = example_packet()
    restored = from_wire(to_wire(packet))
    assert restored == packet


def test_wire_smaller_than_readable_json() -> None:
    packet = example_packet()
    json_size = len(packet.model_dump_json().encode("utf-8"))
    assert wire_size(packet) < json_size


def test_wire_size_and_monthly_data_budget() -> None:
    packet = example_packet()
    size = wire_size(packet)
    # If this guard starts failing, the packet has grown enough that the
    # LTE-M data budget (and the per-truck pricing built on it) needs
    # updating too -- treat it as a business-model change, not just a
    # schema tweak.
    assert size <= 450
    assert monthly_mb(size) <= 20.0
