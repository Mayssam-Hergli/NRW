from __future__ import annotations

import inspect
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from postgrest.exceptions import APIError
from supabase import create_client

from ingest import service as ingest_service
from ingest.store import Store
from ingest.supabase_store import SupabaseStore
from shared.enums import AlertState, FaultCause, Outcome, PrescribedAction, Severity
from shared.schema import AlertRecord, example_packet

# --- live-project gating ----------------------------------------------
#
# Tests 2-9 need a real Supabase project with infra/schema.sql and
# infra/rls.sql already applied -- there's no meaningful way to fake
# Postgres RLS semantics in-process. They're marked `supabase_live` (so
# `pytest -m "not supabase_live"` excludes them explicitly) and also
# self-skip via _require_live() when the env vars aren't set, so a plain
# `pytest` run stays green with nothing configured.


def _live_creds() -> tuple[str, str, str] | None:
    url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY")
    anon_key = os.environ.get("SUPABASE_ANON_KEY")
    if not (url and service_key and anon_key):
        return None
    return url, service_key, anon_key


def _require_live() -> tuple[str, str, str]:
    creds = _live_creds()
    if creds is None:
        pytest.skip("SUPABASE_URL / SUPABASE_SERVICE_KEY / SUPABASE_ANON_KEY not set")
    return creds


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _sample_alert(alert_id: str, device_id: str) -> AlertRecord:
    issued_ts = datetime(2026, 1, 1, tzinfo=UTC)
    return AlertRecord(
        alert_id=alert_id,
        device_id=device_id,
        shipment_id="SHIP-TEST",
        issued_ts=issued_ts,
        tier=1,
        state=AlertState.watch,
        severity=Severity.watch,
        cause=FaultCause.door_unsecured,
        evidence={"door_open_s": 45.0},
        prescribed_action=PrescribedAction.close_door,
        message="Door has been open for 45s.",
    )


@pytest.fixture
def admin_store():
    url, service_key, _ = _require_live()
    store = SupabaseStore.open(url, service_key)
    device_ids: list[str] = []
    alert_ids: list[str] = []
    yield store, device_ids, alert_ids
    for device_id in device_ids:
        store._client.table("telemetry").delete().eq("device_id", device_id).execute()  # noqa: SLF001
    for alert_id in alert_ids:
        store._client.table("alerts").delete().eq("alert_id", alert_id).execute()  # noqa: SLF001
    store.close()


# --- 1: interface parity (no live project needed) ----------------------


def test_supabase_store_has_same_public_interface_as_store() -> None:
    def public_names(cls: type) -> set[str]:
        return {
            name
            for name in dir(cls)
            if not name.startswith("_") and callable(getattr(cls, name))
        }

    store_names = public_names(Store)
    supabase_names = public_names(SupabaseStore)
    assert store_names == supabase_names

    for name in store_names - {"open"}:  # open()'s params legitimately differ (path vs url+key)
        store_params = list(inspect.signature(getattr(Store, name)).parameters)
        supabase_params = list(inspect.signature(getattr(SupabaseStore, name)).parameters)
        assert store_params == supabase_params, name


# --- 2-5: same behavior as Store, against a live project ----------------


@pytest.mark.supabase_live
def test_insert_and_retrieve_roundtrips_packet(admin_store) -> None:
    store, device_ids, _ = admin_store
    packet = example_packet().model_copy(update={"device_id": _unique("dev"), "seq": 0})
    device_ids.append(packet.device_id)

    assert store.insert_packet(packet) is True
    assert store.latest(packet.device_id) == packet


@pytest.mark.supabase_live
def test_duplicate_seq_returns_false_and_stores_one_row(admin_store) -> None:
    store, device_ids, _ = admin_store
    packet = example_packet().model_copy(update={"device_id": _unique("dev"), "seq": 0})
    device_ids.append(packet.device_id)

    assert store.insert_packet(packet) is True
    assert store.insert_packet(packet) is False
    assert len(store.packets(packet.device_id)) == 1


@pytest.mark.supabase_live
def test_out_of_order_inserts_return_in_ts_order(admin_store) -> None:
    store, device_ids, _ = admin_store
    base = example_packet()
    device_id = _unique("dev")
    device_ids.append(device_id)

    p1 = base.model_copy(update={"device_id": device_id, "seq": 1, "ts": base.ts})
    p2 = base.model_copy(
        update={"device_id": device_id, "seq": 2, "ts": base.ts + timedelta(minutes=1)}
    )
    p3 = base.model_copy(
        update={"device_id": device_id, "seq": 3, "ts": base.ts + timedelta(minutes=2)}
    )
    for packet in (p3, p1, p2):
        store.insert_packet(packet)

    assert [p.seq for p in store.packets(device_id)] == [1, 2, 3]


@pytest.mark.supabase_live
def test_gaps_finds_deliberate_hole(admin_store) -> None:
    store, device_ids, _ = admin_store
    base = example_packet()
    device_id = _unique("dev")
    device_ids.append(device_id)

    seq = 0
    ts = base.ts
    for _ in range(5):
        store.insert_packet(base.model_copy(update={"device_id": device_id, "seq": seq, "ts": ts}))
        seq += 1
        ts += timedelta(seconds=60)
    ts += timedelta(minutes=25)
    for _ in range(5):
        store.insert_packet(base.model_copy(update={"device_id": device_id, "seq": seq, "ts": ts}))
        seq += 1
        ts += timedelta(seconds=60)

    gaps = store.gaps(device_id, expected_interval_s=60)
    assert len(gaps) == 1
    start, end = gaps[0]
    assert (end - start) >= timedelta(minutes=25)


# --- 6-7: anon key is read-only ------------------------------------------


@pytest.mark.supabase_live
def test_anonymous_key_cannot_insert_telemetry() -> None:
    url, _, anon_key = _require_live()
    anon_store = SupabaseStore.open(url, anon_key)
    packet = example_packet().model_copy(update={"device_id": _unique("dev-anon"), "seq": 0})

    with pytest.raises(APIError):
        anon_store.insert_packet(packet)


@pytest.mark.supabase_live
def test_anonymous_key_cannot_update_alert(admin_store) -> None:
    store, _, alert_ids = admin_store
    url, _, anon_key = _require_live()
    alert = _sample_alert(_unique("alert"), _unique("dev"))
    alert_ids.append(alert.alert_id)
    store.insert_alert(alert)

    anon_store = SupabaseStore.open(url, anon_key)
    acked = alert.model_copy(
        update={
            "state": AlertState.acknowledged,
            "ack_ts": alert.issued_ts + timedelta(seconds=30),
        }
    )
    with pytest.raises(APIError):
        anon_store.update_alert(acked)


# --- 8: authenticated user, acknowledgment columns only ------------------


@pytest.mark.supabase_live
def test_authenticated_user_can_update_only_ack_fields(admin_store) -> None:
    store, _, alert_ids = admin_store
    url, service_key, anon_key = _require_live()
    alert = _sample_alert(_unique("alert"), _unique("dev"))
    alert_ids.append(alert.alert_id)
    store.insert_alert(alert)

    admin_client = create_client(url, service_key)
    email, password = f"{_unique('user')}@example.com", "Test-Password-123!"
    created = admin_client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    try:
        auth_client = create_client(url, anon_key)
        auth_client.auth.sign_in_with_password({"email": email, "password": password})

        # A narrow update touching only the granted acknowledgment columns --
        # what a (not built here) frontend would send directly.
        ack_ts = alert.issued_ts + timedelta(seconds=30)
        auth_client.table("alerts").update(
            {"ack_ts": ack_ts.isoformat(), "outcome": Outcome.recovered.value}
        ).eq("alert_id", alert.alert_id).execute()

        row = (
            store._client.table("alerts")  # noqa: SLF001 -- service-role read to verify raw columns
            .select("ack_ts, outcome, cause")
            .eq("alert_id", alert.alert_id)
            .single()
            .execute()
            .data
        )
        assert row["ack_ts"] is not None
        assert row["outcome"] == Outcome.recovered.value
        assert row["cause"] == alert.cause.value  # untouched

        # A column outside the grant must be rejected outright.
        with pytest.raises(APIError):
            auth_client.table("alerts").update({"cause": FaultCause.unit_off.value}).eq(
                "alert_id", alert.alert_id
            ).execute()
    finally:
        admin_client.auth.admin.delete_user(created.user.id)


# --- 9: profiles are private to their owner -------------------------------


@pytest.mark.supabase_live
def test_user_cannot_read_another_users_profile_row() -> None:
    url, service_key, anon_key = _require_live()
    admin_client = create_client(url, service_key)
    password = "Test-Password-123!"
    created_users = []

    try:
        emails = [f"{_unique('user')}@example.com" for _ in range(2)]
        for i, email in enumerate(emails):
            created = admin_client.auth.admin.create_user(
                {"email": email, "password": password, "email_confirm": True}
            )
            created_users.append(created.user)
            admin_client.table("profiles").insert(
                {
                    "id": created.user.id,
                    "role": "driver",
                    "locale": "fr",
                    "display_name": f"Driver {i}",
                }
            ).execute()

        client_a = create_client(url, anon_key)
        client_a.auth.sign_in_with_password({"email": emails[0], "password": password})

        result = client_a.table("profiles").select("*").eq("id", created_users[1].id).execute()
        assert result.data == []  # RLS makes the other user's row invisible, not an error

        own = client_a.table("profiles").select("*").eq("id", created_users[0].id).execute()
        assert len(own.data) == 1
    finally:
        for user in created_users:
            admin_client.auth.admin.delete_user(user.id)


# --- 10: backend switch, no live project needed ---------------------------


def test_switching_store_backend_selects_correct_class(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "switch.db"))
    sqlite_store = ingest_service.build_store()
    assert isinstance(sqlite_store, Store)
    sqlite_store.close()

    # create_client() doesn't make a network call -- constructing a
    # SupabaseStore this way is safe with fake credentials.
    monkeypatch.setenv("STORE_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://fake-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "fake-service-key")
    supabase_store = ingest_service.build_store()
    assert isinstance(supabase_store, SupabaseStore)
