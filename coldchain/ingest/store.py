from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from shared.schema import AlertRecord, TelemetryPacket

_SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    shipment_id TEXT,
    ts INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    buffered INTEGER NOT NULL,
    received_ts INTEGER NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(device_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_telemetry_device_ts ON telemetry(device_id, ts);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    shipment_id TEXT,
    issued_ts INTEGER NOT NULL,
    state TEXT NOT NULL,
    severity TEXT NOT NULL,
    cause TEXT NOT NULL,
    payload TEXT NOT NULL,
    ack_ts INTEGER,
    outcome TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_device_issued ON alerts(device_id, issued_ts);
"""


def _to_epoch(ts: datetime) -> int:
    return int(ts.timestamp())


def _from_epoch(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, tz=UTC)


class Store:
    """SQLite-backed persistence for telemetry packets and alerts.

    Packets and alerts are stored whole as JSON in a payload column; the
    surrounding columns exist only to index and filter. Structure lives in
    the query layer, not in the table shape, so shared/schema.py can grow
    fields without a migration here.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.Lock()

    @classmethod
    def open(cls, path: str | Path) -> Store:
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        conn.commit()
        return cls(conn)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def insert_packet(self, packet: TelemetryPacket) -> bool:
        """Insert a packet. Returns False on a (device_id, seq) duplicate."""
        received_ts = _to_epoch(datetime.now(UTC))
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    "INSERT INTO telemetry "
                    "(device_id, shipment_id, ts, seq, buffered, received_ts, payload) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        packet.device_id,
                        packet.shipment_id,
                        _to_epoch(packet.ts),
                        packet.seq,
                        int(packet.buffered),
                        received_ts,
                        packet.model_dump_json(),
                    ),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def insert_alert(self, alert: AlertRecord) -> bool:
        """Insert an alert. Returns False if alert_id already exists."""
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    "INSERT INTO alerts "
                    "(alert_id, device_id, shipment_id, issued_ts, state, severity, cause, "
                    "payload, ack_ts, outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        alert.alert_id,
                        alert.device_id,
                        alert.shipment_id,
                        _to_epoch(alert.issued_ts),
                        alert.state.value,
                        alert.severity.value,
                        alert.cause.value,
                        alert.model_dump_json(),
                        _to_epoch(alert.ack_ts) if alert.ack_ts else None,
                        alert.outcome.value,
                    ),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def update_alert(self, alert: AlertRecord) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE alerts SET device_id=?, shipment_id=?, issued_ts=?, state=?, "
                "severity=?, cause=?, payload=?, ack_ts=?, outcome=? WHERE alert_id=?",
                (
                    alert.device_id,
                    alert.shipment_id,
                    _to_epoch(alert.issued_ts),
                    alert.state.value,
                    alert.severity.value,
                    alert.cause.value,
                    alert.model_dump_json(),
                    _to_epoch(alert.ack_ts) if alert.ack_ts else None,
                    alert.outcome.value,
                    alert.alert_id,
                ),
            )

    def packets(
        self,
        device_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[TelemetryPacket]:
        query = "SELECT payload FROM telemetry WHERE device_id = ?"
        params: list[object] = [device_id]
        if since is not None:
            query += " AND ts >= ?"
            params.append(_to_epoch(since))
        if until is not None:
            query += " AND ts <= ?"
            params.append(_to_epoch(until))
        query += " ORDER BY ts ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [TelemetryPacket.model_validate_json(row[0]) for row in rows]

    def latest(self, device_id: str) -> TelemetryPacket | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM telemetry WHERE device_id = ? ORDER BY ts DESC LIMIT 1",
                (device_id,),
            ).fetchone()
        return TelemetryPacket.model_validate_json(row[0]) if row else None

    def shipment(self, shipment_id: str) -> list[TelemetryPacket]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM telemetry WHERE shipment_id = ? ORDER BY ts ASC",
                (shipment_id,),
            ).fetchall()
        return [TelemetryPacket.model_validate_json(row[0]) for row in rows]

    def alerts(
        self, device_id: str | None = None, state: str | None = None
    ) -> list[AlertRecord]:
        query = "SELECT payload FROM alerts WHERE 1=1"
        params: list[object] = []
        if device_id is not None:
            query += " AND device_id = ?"
            params.append(device_id)
        if state is not None:
            query += " AND state = ?"
            params.append(state.value if hasattr(state, "value") else state)
        query += " ORDER BY issued_ts ASC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [AlertRecord.model_validate_json(row[0]) for row in rows]

    def gaps(
        self, device_id: str, expected_interval_s: int = 60
    ) -> list[tuple[datetime, datetime]]:
        """Consecutive-packet time gaps wider than 2x the expected interval."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts FROM telemetry WHERE device_id = ? ORDER BY ts ASC",
                (device_id,),
            ).fetchall()
        threshold = expected_interval_s * 2
        found: list[tuple[datetime, datetime]] = []
        for (prev,), (curr,) in zip(rows, rows[1:], strict=False):
            if curr - prev > threshold:
                found.append((_from_epoch(prev), _from_epoch(curr)))
        return found
