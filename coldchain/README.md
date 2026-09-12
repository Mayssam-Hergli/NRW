# Cold Chain Integrity System

Cold chain integrity monitoring for pharmaceutical road distribution in
Tunisia. An in-vehicle gateway (ESP32-S3 + LTE-M modem) senses cargo
temperature at multiple points, the refrigeration unit's current and
voltage, GNSS position and speed, door state, light and shock. It reduces
high-rate sensing to a small feature packet each minute, runs a local
thermal model so it can alert the driver with no network, buffers to flash
when offline, signs packets, and uplinks over MQTT/TLS. The cloud enriches
telemetry with weather along the route, runs four diagnostic models, fuses
them into a diagnosis with a prescribed action, alerts the driver and
dispatcher, and generates compliance certificates.

## The three contracts

Everything downstream imports `shared/`. These three Pydantic models,
defined in [shared/schema.py](shared/schema.py), are the interface between
firmware, ingest, models, API, and dashboard.

| Contract | Direction | Purpose |
|---|---|---|
| `TelemetryPacket` | device → cloud | One minute of fused sensor state: cargo temps, ambient, door, light, shock, refrigeration power, GNSS, device health. |
| `AlertRecord` | device → cloud, cloud → dispatcher | A diagnosed fault with severity, cause, prescribed action, and acknowledgement/outcome lifecycle. |
| `ConfigDownlink` | cloud → device | Sampling and uplink cadence, waveform capture, and local alert thresholds pushed to a device. |

Mission profiles (`shared/profiles.py`) parameterize the acceptable band and
excursion limits per cargo type: `pharma_refrigerated`, `pharma_frozen`,
`controlled_room_temp`, `vaccines`, `fresh_produce`. Notably, `vaccines` sets
`freeze_alarm=True` even though its band (2-8C) sits well above freezing —
vaccines are destroyed by freezing more often than by heat, and a profile
that only watches the upper bound misses that failure mode.

## Wire format

`shared/wire.py` implements the CBOR encoding a device actually uplinks:
single-character field keys, epoch-second timestamps, and null fields
dropped entirely.

Measured on `example_packet()`:

- Readable JSON: **828 bytes**
- Wire (CBOR, short keys): **406 bytes**
- At a 60s uplink interval: **~17.5 MB/truck/month**

The 400-800 byte range is not a rounding error — it is the difference
between roughly 1.50 USD and 3 USD of LTE-M data per truck per month. The
wire format is a business requirement, not an optimization; if
`example_packet()` ever grows past ~450 bytes on the wire, the per-truck
data budget (and the pricing built on it) needs revisiting, not just the
schema.

## Running tests

```
pip install -e ".[dev]"
pytest
ruff check .
```

## Directory map

```
shared/       Frozen data contract: enums, mission profiles, schema, wire codec.
simulator/    Synthetic fleet + fault scenario generator. (not yet implemented)
ingest/       MQTT/TLS broker-facing ingest service. (not yet implemented)
models/       Thermal, electrical, and fusion diagnostic models. (not yet implemented)
api/          Cloud API serving diagnoses, alerts, certificates. (not yet implemented)
reports/      Compliance certificate generation. (not yet implemented)
dashboard/    Driver/dispatcher-facing UI. (not yet implemented)
firmware/     ESP32-S3 gateway firmware. (not yet implemented)
docs/         Design notes.
infra/        Local dev infrastructure (Mosquitto broker config).
tests/        Tests for shared/.
```

## shared/ is frozen

`shared/` is the interface that firmware, ingest, models, API, and dashboard
all import in parallel. Do not change field names, types, enum values, or
validators in `shared/` without agreement from all workstreams that consume
it — a silent change here breaks builds that aren't in front of you.
