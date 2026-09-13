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

## Storage backend: SQLite or Supabase

`ingest/store.py` (`Store`, SQLite) and `ingest/supabase_store.py`
(`SupabaseStore`, hosted Postgres) expose the exact same instance
interface — `insert_packet`, `insert_alert`, `update_alert`, `packets`,
`latest`, `shipment`, `alerts`, `gaps`, `close`. `ingest/service.py` picks
one via `build_store()`, based on `STORE_BACKEND`; nothing else in the
ingest pipeline knows or cares which backend it's talking to.

Supabase exists so the demo can put a QR code on screen: the simulator and
models keep running locally, but the phones in the room need a hosted
database they can subscribe to directly, and Supabase Realtime is that
WebSocket layer, already built.

### Env vars

| Var | Used by | Notes |
|---|---|---|
| `STORE_BACKEND` | ingest | `sqlite` (default) or `supabase` |
| `DB_PATH` | ingest, sqlite backend | path to the local `.db` file |
| `SUPABASE_URL` | ingest, supabase backend | `https://<project-ref>.supabase.co` |
| `SUPABASE_SERVICE_KEY` | ingest, supabase backend | service-role key — bypasses RLS entirely |
| `SUPABASE_ANON_KEY` | dashboard | public, read-only under RLS — safe to ship in a static build |

**`SUPABASE_SERVICE_KEY` never enters the repo or the static frontend
build.** It is the one credential that bypasses row-level security
outright, held only by the local ingest process, passed in as an
environment variable at runtime. `SUPABASE_ANON_KEY` is the only Supabase
key a browser should ever see — it's designed to ship inside a public
static site, and `infra/rls.sql` is what makes that safe.

### One-time project setup

1. Create a Supabase project.
2. In the SQL Editor (or via the CLI), run `infra/schema.sql`, then
   `infra/rls.sql`, in that order — the tables have to exist before the
   policies referencing them can be created.
3. Enable email/password sign-in under Authentication if you want to
   exercise the `authenticated`-role tests or flows (no accounts or
   passwords live in this repo; `profiles.role`/`profiles.locale` just
   drive what a signed-in user's dashboard shows).
4. Copy the project URL, the `service_role` key, and the `anon` key into
   your environment (never into a committed file):

   ```
   export STORE_BACKEND=supabase
   export SUPABASE_URL=https://<project-ref>.supabase.co
   export SUPABASE_SERVICE_KEY=<service-role key>
   export SUPABASE_ANON_KEY=<anon key>
   ```

5. Run ingest against it exactly as with SQLite:

   ```
   python -m ingest.service
   ```

### Running the Supabase tests

`tests/test_supabase_store.py` has ten tests. Two (interface parity,
backend switching) run with no configuration at all. The other eight
need a real project with the schema and RLS already applied — they're
marked `supabase_live` and self-skip when the env vars above aren't set:

```
pytest tests/test_supabase_store.py            # skips the live ones cleanly
pytest tests/test_supabase_store.py -m supabase_live   # only the live ones
```

The live tests create and delete their own throwaway rows/users
(prefixed with a random suffix) against whatever project the env vars
point at — don't point them at a project with data you care about.

## Directory map

```
shared/       Frozen data contract: enums, mission profiles, schema, wire codec.
simulator/    Synthetic fleet, fault scenarios, MQTT publisher, and database seeder.
ingest/       MQTT ingest service with interchangeable SQLite and Supabase stores.
models/       Thermal, electrical, MKT/stability, fusion, and alert lifecycle models.
api/          Reserved for a cloud HTTP API; currently empty.
reports/      Multilingual PDF compliance-certificate generation.
dashboard/    React driver, dispatcher, and quality UI using Supabase Auth + Realtime.
firmware/     Reserved for the ESP32-S3 gateway firmware; currently empty.
docs/         Reserved for design notes; currently empty.
infra/        Mosquitto configuration plus Supabase schema and RLS policies.
tests/        Python tests spanning contracts, simulation, ingest, models, and reports.
```

## shared/ is frozen

`shared/` is the interface that firmware, ingest, models, API, and dashboard
all import in parallel. Do not change field names, types, enum values, or
validators in `shared/` without agreement from all workstreams that consume
it — a silent change here breaks builds that aren't in front of you.
