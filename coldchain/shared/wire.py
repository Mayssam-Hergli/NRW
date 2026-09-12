from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

import cbor2

from shared.schema import TelemetryPacket

# Every field name that can appear anywhere inside a TelemetryPacket (top
# level or nested) maps to a unique single character on the wire. This is
# what gets a ~700 byte readable JSON packet down to ~400 bytes of CBOR,
# which is the difference between a truck costing ~1.50 USD/month of LTE-M
# data and ~3 USD/month. See shared/wire.py module docstring in README for
# the business rationale.
FIELD_KEY_MAP: dict[str, str] = {
    "ambient_c": "a",
    "band": "b",
    "batt_v": "c",
    "buffer_pct": "d",
    "buffered": "e",
    "cargo": "f",
    "compressor": "g",
    "cond_fan": "h",
    "device_id": "i",
    "door": "j",
    "duty_pct": "k",
    "evap_fan": "l",
    "events": "m",
    "fix": "n",
    "gnss": "o",
    "gnss_fix": "p",
    "health": "q",
    "i_rms": "r",
    "inrush_peak": "s",
    "lat": "t",
    "light_lux": "u",
    "lon": "v",
    "max_c": "w",
    "min_c": "x",
    "mission_profile": "y",
    "motion": "z",
    "open": "A",
    "peak_g": "B",
    "pos": "C",
    "power": "D",
    "rh": "E",
    "rssi": "F",
    "seq": "G",
    "shipment_id": "H",
    "shock_events": "I",
    "sig": "J",
    "speed_kmh": "K",
    "state": "L",
    "t_c": "M",
    "tag": "N",
    "ts": "O",
    "v_bus": "P",
    "vib_rms": "Q",
}

REVERSE_FIELD_KEY_MAP: dict[str, str] = {v: k for k, v in FIELD_KEY_MAP.items()}

if len(REVERSE_FIELD_KEY_MAP) != len(FIELD_KEY_MAP):
    raise RuntimeError("FIELD_KEY_MAP has colliding single-character values")


def _shorten(value: Any) -> Any:
    if isinstance(value, dict):
        return {FIELD_KEY_MAP[k]: _shorten(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_shorten(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _lengthen(value: Any) -> Any:
    if isinstance(value, dict):
        return {REVERSE_FIELD_KEY_MAP[k]: _lengthen(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_lengthen(v) for v in value]
    return value


def to_wire(packet: TelemetryPacket) -> bytes:
    data = packet.model_dump(mode="python")
    data["ts"] = int(packet.ts.timestamp())
    return cbor2.dumps(_shorten(data))


def from_wire(blob: bytes) -> TelemetryPacket:
    data = _lengthen(cbor2.loads(blob))
    data["ts"] = datetime.fromtimestamp(data["ts"], tz=UTC)
    return TelemetryPacket.model_validate(data)


def wire_size(packet: TelemetryPacket) -> int:
    return len(to_wire(packet))


def monthly_mb(packet_bytes: int, uplink_interval_s: int = 60) -> float:
    seconds_per_month = 30 * 24 * 3600
    packets_per_month = seconds_per_month / uplink_interval_s
    total_bytes = packet_bytes * packets_per_month
    return total_bytes / 1_000_000
