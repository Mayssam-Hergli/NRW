from __future__ import annotations

import io
from collections import deque
from datetime import UTC, datetime, timedelta

import pytest
from pypdf import PdfReader

from ingest.store import Store
from models.alert_engine import AlertEngine
from models.electrical_health import ElectricalHealthMonitor
from models.fusion import fuse
from models.m1_thermal import M1ThermalForecast
from models.m3_mkt import Verdict, readings_from_packets, stability_budget_consumed
from reports.certificate import (
    CertificateError,
    build_certificate,
    chart_series,
    compute_summary,
    event_log_rows,
    gather_shipment_data,
    verification_hash,
)
from reports.templates import VERDICT_LABEL
from shared.enums import AlertState, FaultCause, PrescribedAction, Severity
from shared.schema import AlertRecord
from simulator.electrical import ElectricalSim
from simulator.scenarios import DoorOpenScenario, NominalScenario
from tests.test_fusion import _packet

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "".join(page.extract_text() or "" for page in reader.pages)


def _normalized(text: str) -> str:
    """Collapse whitespace/newlines -- a narrow event-log table cell wraps a
    multi-word label onto two lines, which pypdf's extract_text() then
    reports with a newline where the label itself only has a space."""
    return " ".join(text.split())


def _run_scenario_with_alerts(cls, store, duration_min: float | None = None) -> str:
    """Run one scenario through the same fusion + alert-engine pipeline
    simulator/seed.py uses, inserting packets and alerts into `store`.
    Returns the shipment_id."""
    scenario = cls()
    packets = list(scenario.run(duration_min=duration_min, dt_s=60.0))

    m1 = M1ThermalForecast()
    m2 = ElectricalHealthMonitor(dt_min=1.0)
    elec = ElectricalSim(scenario.profile)
    engine = AlertEngine()
    history = deque(maxlen=30)
    seen_alert_ids: set[str] = set()

    for packet in packets:
        store.insert_packet(packet)
        r1 = m1.update(packet)
        expected_duty = elec.expected_duty_pct(packet.ambient_c, packet.gnss.speed_kmh)
        r2 = m2.update(packet, expected_duty)
        diagnosis = fuse(packet, r1, r2, None, list(history))
        for record in engine.update(packet, diagnosis):
            if record.alert_id in seen_alert_ids:
                store.update_alert(record)
            else:
                store.insert_alert(record)
                seen_alert_ids.add(record.alert_id)
        history.append(packet)

    return scenario.shipment_id


# --- 1/2: verdict is CONFORME for a healthy run, EXCURSION for door_open ---


def test_nominal_shipment_certificate_is_conforme(tmp_path) -> None:
    store = Store.open(tmp_path / "test.db")
    scenario = NominalScenario()
    for packet in scenario.run(dt_s=60.0):
        store.insert_packet(packet)

    pdf_bytes = build_certificate(scenario.shipment_id, store, locale="fr")
    text = _extract_text(pdf_bytes)

    assert VERDICT_LABEL[Verdict.compliant]["fr"] in text
    record = gather_shipment_data(scenario.shipment_id, store)
    assert compute_summary(record.packets, record.profile).budget.verdict == Verdict.compliant


def test_door_open_shipment_certificate_is_excursion_review(tmp_path) -> None:
    store = Store.open(tmp_path / "test.db")
    scenario = DoorOpenScenario()
    for packet in scenario.run(dt_s=60.0):
        store.insert_packet(packet)

    pdf_bytes = build_certificate(scenario.shipment_id, store, locale="fr")
    text = _extract_text(pdf_bytes)

    assert VERDICT_LABEL[Verdict.excursion_review]["fr"] in text
    record = gather_shipment_data(scenario.shipment_id, store)
    budget = compute_summary(record.packets, record.profile).budget
    assert budget.verdict == Verdict.excursion_review


# --- 3: the PDF is a real, non-trivial document ----------------------------


def test_pdf_is_valid_and_non_trivial(tmp_path) -> None:
    store = Store.open(tmp_path / "test.db")
    scenario = NominalScenario()
    for packet in scenario.run(dt_s=60.0):
        store.insert_packet(packet)

    pdf_bytes = build_certificate(scenario.shipment_id, store)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1

    text = "".join(page.extract_text() or "" for page in reader.pages)
    assert len(text) > 200
    assert scenario.shipment_id in text


# --- 4: a gap shows reduced coverage and a broken chart, never a bridge ----


def test_gap_reduces_coverage_and_breaks_the_chart(tmp_path) -> None:
    store = Store.open(tmp_path / "test.db")
    scenario = NominalScenario()
    packets = list(scenario.run(dt_s=60.0))

    # Drop a 25-minute stretch out of the middle -- a genuine, unobserved
    # gap, not a buffered/replayed one.
    kept = [p for p in packets if not (200 <= p.seq < 225)]
    for packet in kept:
        store.insert_packet(packet)

    record = gather_shipment_data(scenario.shipment_id, store)
    summary = compute_summary(record.packets, record.profile)
    assert summary.budget.coverage_pct < 100.0

    series = chart_series(record.packets)
    assert any(len(segments) >= 2 for segments in series.values()), (
        "expected at least one probe's line to break into multiple segments "
        "across the dropped 25-minute window"
    )

    pdf_bytes = build_certificate(scenario.shipment_id, store)
    text = _extract_text(pdf_bytes)
    assert f"{summary.budget.coverage_pct:.1f}" in text


# --- 5/6: every alert appears in the event log, suppressed ones included --


def test_every_fusion_alert_appears_in_event_log(tmp_path) -> None:
    store = Store.open(tmp_path / "test.db")
    shipment_id = _run_scenario_with_alerts(DoorOpenScenario, store)

    record = gather_shipment_data(shipment_id, store)
    assert record.alerts, "expected door_open to produce at least one alert"

    rows = event_log_rows(record.alerts, "fr")
    assert len(rows) == len(record.alerts)

    pdf_bytes = build_certificate(shipment_id, store)
    text = _normalized(_extract_text(pdf_bytes))
    # Every alert's own rendered cause label shows up in the PDF text --
    # nothing in the event log was silently dropped or filtered.
    for row in rows:
        assert _normalized(row.cause) in text


def test_suppressed_events_show_suppression_reason() -> None:
    # The store keeps only the latest row per alert_id (ingest/store.py's
    # alerts table is keyed on alert_id, not an append-only event log), so
    # a shipment that later escalates never shows its own earlier suppressed
    # state once stored -- see models/alert_engine.py's own docstring on the
    # offload_stop/door_unsecured group sharing one alert_id. event_log_rows()
    # itself doesn't know or care about that storage detail, so it's tested
    # directly against a still-suppressed AlertRecord, exactly the shape a
    # shipment that ends *before* its dwell limit would actually store.
    suppression_reason = "door open 4 min, within the 10-min offload dwell limit"
    suppressed_alert = AlertRecord(
        alert_id="a-door",
        device_id="TEST-GW",
        shipment_id="SHIP-TEST",
        issued_ts=BASE,
        tier=1,
        state=AlertState.suppressed,
        severity=Severity.watch,
        cause=FaultCause.offload_stop,
        evidence={"door_open_min": 4.0},
        prescribed_action=PrescribedAction.call_dispatch,
        message=suppression_reason,
    )
    warning_alert = _sample_alert()

    rows = event_log_rows([suppressed_alert, warning_alert], "fr")
    suppressed_row, warning_row = rows

    assert suppressed_row.note
    assert suppression_reason in suppressed_row.note
    assert warning_row.note == ""


# --- 7: verification hash is deterministic and change-sensitive -----------


def _sample_alert() -> AlertRecord:
    return AlertRecord(
        alert_id="a1",
        device_id="TEST-GW",
        shipment_id="SHIP-TEST",
        issued_ts=BASE,
        tier=1,
        state=AlertState.warning,
        severity=Severity.warning,
        cause=FaultCause.refrigerant_loss,
        evidence={"dev_pp": 20.0},
        prescribed_action=PrescribedAction.schedule_service,
        message="Cooling weakened.",
    )


def test_verification_hash_deterministic_and_change_sensitive() -> None:
    packet = _packet(t_c=5.0, seq=0)
    alert = _sample_alert()

    h1 = verification_hash([packet], [alert])
    h2 = verification_hash([packet], [alert])
    assert h1 == h2

    changed_packet = packet.model_copy(update={"ambient_c": packet.ambient_c + 1.0})
    assert verification_hash([changed_packet], [alert]) != h1

    changed_alert = alert.model_copy(update={"evidence": {"dev_pp": 21.0}})
    assert verification_hash([packet], [changed_alert]) != h1


# --- 8: fr and en differ, numeric values identical -------------------------


def test_fr_and_en_event_log_differ_with_identical_numeric_values() -> None:
    alert = _sample_alert()
    fr_row = event_log_rows([alert], "fr")[0]
    en_row = event_log_rows([alert], "en")[0]

    assert fr_row.cause != en_row.cause
    assert fr_row.action != en_row.action
    assert fr_row.severity != en_row.severity
    # The numbers inside evidence are locale-independent.
    assert fr_row.evidence == en_row.evidence == "dev_pp=20.00"


# --- 9: the verdict in the PDF is exactly M3's own verdict -----------------


def test_verdict_matches_m3_exactly(tmp_path) -> None:
    store = Store.open(tmp_path / "test.db")
    scenario = DoorOpenScenario()
    packets = list(scenario.run(dt_s=60.0))
    for packet in packets:
        store.insert_packet(packet)

    stored = store.shipment(scenario.shipment_id)
    readings = readings_from_packets(stored)
    duration_min = (stored[-1].ts - stored[0].ts).total_seconds() / 60.0
    expected = stability_budget_consumed(readings, scenario.profile, duration_min)

    record = gather_shipment_data(scenario.shipment_id, store)
    actual = compute_summary(record.packets, record.profile).budget
    assert actual == expected

    pdf_bytes = build_certificate(scenario.shipment_id, store, locale="en")
    text = _extract_text(pdf_bytes)
    assert VERDICT_LABEL[expected.verdict]["en"] in text


# --- locale gap: ar is a documented rejection, not a broken layout ---------


def test_arabic_locale_is_rejected_not_silently_broken(tmp_path) -> None:
    store = Store.open(tmp_path / "test.db")
    scenario = NominalScenario()
    for packet in scenario.run(dt_s=60.0):
        store.insert_packet(packet)

    with pytest.raises(CertificateError):
        build_certificate(scenario.shipment_id, store, locale="ar")


# --- 10: seed.py writes six distinct, backdated shipments ------------------


def test_seed_writes_six_shipments_with_distinct_devices_and_backdated_ts(tmp_path) -> None:
    from simulator.seed import seed

    store = Store.open(tmp_path / "test.db")
    out_dir = tmp_path / "certs"
    now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

    results = seed(store, out_dir=out_dir, now=now)

    assert len(results) == 6
    device_ids = {r["device_id"] for r in results}
    assert len(device_ids) == 6

    start_times = []
    for r in results:
        stored = store.shipment(r["shipment_id"])
        assert stored, r["shipment_id"]
        start_times.append(min(p.ts for p in stored))
        assert r["certificate_path"].exists()

    assert max(start_times) - min(start_times) > timedelta(days=1)
    assert all(ts < now for ts in start_times), "seeded shipments must be backdated, not future"
