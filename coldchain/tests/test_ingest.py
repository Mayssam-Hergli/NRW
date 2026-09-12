from __future__ import annotations

from datetime import timedelta

from ingest.service import IngestService, decode_telemetry
from ingest.store import Store
from shared.enums import AlertState, FaultCause, PrescribedAction, Severity
from shared.schema import AlertRecord, example_packet
from shared.wire import to_wire


def _store(tmp_path):
    return Store.open(tmp_path / "test.db")


def test_insert_and_retrieve_roundtrip(tmp_path) -> None:
    store = _store(tmp_path)
    packet = example_packet()
    assert store.insert_packet(packet) is True
    retrieved = store.latest(packet.device_id)
    assert retrieved == packet


def test_duplicate_seq_rejected_and_stores_one_row(tmp_path) -> None:
    store = _store(tmp_path)
    packet = example_packet()
    assert store.insert_packet(packet) is True
    assert store.insert_packet(packet) is False
    rows = store.packets(packet.device_id)
    assert len(rows) == 1


def test_packets_returned_in_ts_order_despite_insertion_order(tmp_path) -> None:
    store = _store(tmp_path)
    base = example_packet()
    p1 = base.model_copy(update={"seq": 1, "ts": base.ts})
    p2 = base.model_copy(update={"seq": 2, "ts": base.ts + timedelta(minutes=1)})
    p3 = base.model_copy(update={"seq": 3, "ts": base.ts + timedelta(minutes=2)})
    for p in (p3, p1, p2):
        store.insert_packet(p)
    result = store.packets(base.device_id)
    assert [p.seq for p in result] == [1, 2, 3]


def test_buffered_packet_arriving_late_is_retrievable(tmp_path) -> None:
    store = _store(tmp_path)
    base = example_packet()
    buffered = base.model_copy(
        update={"seq": 99, "buffered": True, "ts": base.ts - timedelta(minutes=30)}
    )
    assert store.insert_packet(buffered) is True
    result = store.packets(base.device_id)
    match = next(p for p in result if p.seq == 99)
    assert match.buffered is True


def test_latest_returns_highest_ts_not_last_inserted(tmp_path) -> None:
    store = _store(tmp_path)
    base = example_packet()
    newer = base.model_copy(update={"seq": 1, "ts": base.ts + timedelta(minutes=5)})
    older = base.model_copy(update={"seq": 2, "ts": base.ts})
    store.insert_packet(newer)
    store.insert_packet(older)
    latest = store.latest(base.device_id)
    assert latest is not None
    assert latest.seq == 1


def test_gaps_finds_deliberate_hole(tmp_path) -> None:
    store = _store(tmp_path)
    base = example_packet()
    seq = 0
    ts = base.ts
    for _ in range(5):
        store.insert_packet(base.model_copy(update={"seq": seq, "ts": ts}))
        seq += 1
        ts += timedelta(seconds=60)
    gap_start = ts - timedelta(seconds=60)
    ts += timedelta(minutes=25)
    for _ in range(5):
        store.insert_packet(base.model_copy(update={"seq": seq, "ts": ts}))
        seq += 1
        ts += timedelta(seconds=60)
    gaps = store.gaps(base.device_id, expected_interval_s=60)
    assert len(gaps) == 1
    start, end = gaps[0]
    assert start == gap_start
    assert (end - start) >= timedelta(minutes=25)


def test_shipment_returns_only_that_shipments_packets(tmp_path) -> None:
    store = _store(tmp_path)
    base = example_packet()
    a = base.model_copy(update={"seq": 1, "shipment_id": "SHIP-A"})
    b = base.model_copy(update={"seq": 2, "shipment_id": "SHIP-B"})
    store.insert_packet(a)
    store.insert_packet(b)
    result = store.shipment("SHIP-A")
    assert len(result) == 1
    assert result[0].shipment_id == "SHIP-A"


def test_invalid_payload_is_counted_and_does_not_raise(tmp_path) -> None:
    store = _store(tmp_path)
    service = IngestService(store, host="localhost", port=1883, tenant="acme")
    service._handle_telemetry("DEV1", b"not a valid packet")
    assert service.counters.packets_invalid == 1
    assert service.counters.packets_ok == 0


def test_cbor_and_json_payloads_decode_identically() -> None:
    packet = example_packet()
    cbor_packet, cbor_codec = decode_telemetry(to_wire(packet))
    json_packet, json_codec = decode_telemetry(packet.model_dump_json().encode("utf-8"))
    assert cbor_codec == "cbor"
    assert json_codec == "json"
    assert cbor_packet == json_packet == packet


def test_alert_insert_then_update_preserves_ack_fields(tmp_path) -> None:
    store = _store(tmp_path)
    packet = example_packet()
    alert = AlertRecord(
        alert_id="AL-1",
        device_id=packet.device_id,
        shipment_id=packet.shipment_id,
        issued_ts=packet.ts,
        tier=1,
        state=AlertState.watch,
        severity=Severity.watch,
        cause=FaultCause.door_unsecured,
        evidence={"door_open_s": 45.0},
        prescribed_action=PrescribedAction.close_door,
        message="Door has been open for 45s.",
    )
    assert store.insert_alert(alert) is True

    ack_ts = packet.ts + timedelta(seconds=30)
    acked = alert.model_copy(update={"state": AlertState.acknowledged, "ack_ts": ack_ts})
    store.update_alert(acked)

    result = store.alerts(device_id=packet.device_id)
    assert len(result) == 1
    assert result[0].state == AlertState.acknowledged
    assert result[0].ack_ts == ack_ts
