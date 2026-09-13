"""Supabase Postgres-backed persistence, satisfying the exact same instance
interface as ingest.store.Store so IngestService can use either one
interchangeably based on the STORE_BACKEND env var, with no other code
change (see ingest/service.py's build_store()).

This class never creates or alters schema -- infra/schema.sql and
infra/rls.sql must already be applied to the target Supabase project. It
also never bypasses RLS itself: it authenticates with whatever key it's
given (the service role key for ingest), and Postgres enforces the actual
access rules. See infra/rls.sql and the README for what each key can do.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta

from postgrest.exceptions import APIError
from supabase import Client, create_client

from shared.schema import AlertRecord, TelemetryPacket

# Postgres error code for a unique-constraint violation. insert_packet and
# insert_alert both dedup on this, matching Store's "return False, don't
# raise" contract exactly.
_UNIQUE_VIOLATION = "23505"


def _alert_row(alert: AlertRecord) -> dict[str, object]:
    return {
        "alert_id": alert.alert_id,
        "device_id": alert.device_id,
        "shipment_id": alert.shipment_id,
        "issued_ts": alert.issued_ts.isoformat(),
        "state": alert.state.value,
        "severity": alert.severity.value,
        "cause": alert.cause.value,
        "payload": alert.model_dump(mode="json"),
        "ack_ts": alert.ack_ts.isoformat() if alert.ack_ts else None,
        "driver_cause": alert.driver_cause.value if alert.driver_cause else None,
        "action_taken": alert.action_taken,
        "outcome": alert.outcome.value,
    }


class SupabaseStore:
    def __init__(self, client: Client) -> None:
        self._client = client

    @classmethod
    def open(cls, url: str, key: str) -> SupabaseStore:
        return cls(create_client(url, key))

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._client.postgrest.session.close()

    def insert_packet(self, packet: TelemetryPacket) -> bool:
        """Insert a packet. Returns False on a (device_id, seq) duplicate."""
        row = {
            "device_id": packet.device_id,
            "shipment_id": packet.shipment_id,
            "ts": packet.ts.isoformat(),
            "seq": packet.seq,
            "buffered": packet.buffered,
            "received_ts": datetime.now(UTC).isoformat(),
            "payload": packet.model_dump(mode="json"),
        }
        try:
            self._client.table("telemetry").insert(row).execute()
        except APIError as exc:
            if exc.code == _UNIQUE_VIOLATION:
                return False
            raise
        return True

    def insert_alert(self, alert: AlertRecord) -> bool:
        """Insert an alert. Returns False if alert_id already exists."""
        try:
            self._client.table("alerts").insert(_alert_row(alert)).execute()
        except APIError as exc:
            if exc.code == _UNIQUE_VIOLATION:
                return False
            raise
        return True

    def update_alert(self, alert: AlertRecord) -> None:
        self._client.table("alerts").update(_alert_row(alert)).eq(
            "alert_id", alert.alert_id
        ).execute()

    def packets(
        self,
        device_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[TelemetryPacket]:
        query = self._client.table("telemetry").select("payload").eq("device_id", device_id)
        if since is not None:
            query = query.gte("ts", since.isoformat())
        if until is not None:
            query = query.lte("ts", until.isoformat())
        query = query.order("ts")
        if limit is not None:
            query = query.limit(limit)
        rows = query.execute().data
        return [TelemetryPacket.model_validate(row["payload"]) for row in rows]

    def latest(self, device_id: str) -> TelemetryPacket | None:
        rows = (
            self._client.table("telemetry")
            .select("payload")
            .eq("device_id", device_id)
            .order("ts", desc=True)
            .limit(1)
            .execute()
            .data
        )
        return TelemetryPacket.model_validate(rows[0]["payload"]) if rows else None

    def shipment(self, shipment_id: str) -> list[TelemetryPacket]:
        rows = (
            self._client.table("telemetry")
            .select("payload")
            .eq("shipment_id", shipment_id)
            .order("ts")
            .execute()
            .data
        )
        return [TelemetryPacket.model_validate(row["payload"]) for row in rows]

    def alerts(
        self, device_id: str | None = None, state: str | None = None
    ) -> list[AlertRecord]:
        query = self._client.table("alerts").select("payload")
        if device_id is not None:
            query = query.eq("device_id", device_id)
        if state is not None:
            query = query.eq("state", state.value if hasattr(state, "value") else state)
        rows = query.order("issued_ts").execute().data
        return [AlertRecord.model_validate(row["payload"]) for row in rows]

    def gaps(
        self, device_id: str, expected_interval_s: int = 60
    ) -> list[tuple[datetime, datetime]]:
        """Consecutive-packet time gaps wider than 2x the expected interval."""
        rows = (
            self._client.table("telemetry")
            .select("ts")
            .eq("device_id", device_id)
            .order("ts")
            .execute()
            .data
        )
        threshold = timedelta(seconds=expected_interval_s * 2)
        timestamps = [datetime.fromisoformat(row["ts"]) for row in rows]
        found: list[tuple[datetime, datetime]] = []
        for prev, curr in zip(timestamps, timestamps[1:], strict=False):
            if curr - prev > threshold:
                found.append((prev, curr))
        return found
