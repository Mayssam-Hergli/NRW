-- Supabase Postgres schema, mirroring ingest/store.py's SQLite tables so
-- SupabaseStore behaves identically to Store from the caller's side.
--
-- Run this once against a fresh Supabase project (SQL Editor, or `supabase
-- db push` if you're using the CLI with migrations), then infra/rls.sql.

create table if not exists telemetry (
    id bigint generated always as identity primary key,
    device_id text not null,
    shipment_id text,
    ts timestamptz not null,
    seq integer not null,
    buffered boolean not null default false,
    received_ts timestamptz not null default now(),
    payload jsonb not null,
    unique (device_id, seq)
);

create index if not exists idx_telemetry_device_ts on telemetry (device_id, ts);

create table if not exists alerts (
    alert_id text primary key,
    device_id text not null,
    shipment_id text,
    issued_ts timestamptz not null,
    state text not null,
    severity text not null,
    cause text not null,
    payload jsonb not null,
    ack_ts timestamptz,
    -- driver_cause and action_taken are duplicated out of payload into
    -- real columns (SQLite's mirror keeps them JSON-only) specifically so
    -- infra/rls.sql can grant UPDATE on exactly these acknowledgment
    -- fields -- Postgres column-level privileges only apply to actual
    -- columns, not to keys inside a jsonb blob.
    driver_cause text,
    action_taken text,
    outcome text not null
);

create index if not exists idx_alerts_device_issued on alerts (device_id, issued_ts);

-- One row per authenticated user: role and locale drive what the
-- dashboard shows and in which language (shared/messages.py); no
-- passwords live here, Supabase Auth owns those.
create table if not exists profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    role text not null check (role in ('driver', 'dispatcher', 'quality')),
    locale text not null default 'fr' check (locale in ('fr', 'en', 'ar')),
    display_name text not null,
    created_at timestamptz not null default now()
);

-- Realtime: the QR-code demo subscribes phones directly to these two
-- tables instead of us hand-rolling a WebSocket fan-out layer.
alter publication supabase_realtime add table telemetry;
alter publication supabase_realtime add table alerts;
