-- Row-level security. Run after infra/schema.sql.
--
-- The anon key ships inside a public static site (the QR code jurors scan),
-- so this file -- not the frontend code -- is the actual security boundary
-- between a stranger's phone and the telemetry/alerts tables. Nothing here
-- trusts the client: writes that matter go through the service role, which
-- only the local ingest process holds and which is never sent to a browser.
--
-- Postgres RLS policies gate whole rows. Column-level restriction (the
-- "authenticated users may only touch the acknowledgment fields" rule)
-- is enforced by the SQL privilege system instead (GRANT UPDATE (cols)),
-- alongside the row policy -- both must pass.

alter table telemetry enable row level security;
alter table alerts enable row level security;
alter table profiles enable row level security;

-- ---------------------------------------------------------------------
-- telemetry: read-only for anyone who can reach the API with any key.
-- No INSERT/UPDATE/DELETE policy exists for anon or authenticated, so
-- those operations are denied by RLS's default-deny regardless of the
-- table-level grant; the REVOKE below removes the grant too, so the
-- intent is explicit even without relying on that default.
-- ---------------------------------------------------------------------

create policy "telemetry_select_anon" on telemetry
    for select
    to anon
    using (true);

create policy "telemetry_select_authenticated" on telemetry
    for select
    to authenticated
    using (true);

revoke insert, update, delete on telemetry from anon, authenticated;

-- ---------------------------------------------------------------------
-- alerts: read-only for everyone, plus a narrow acknowledgment path for
-- signed-in users.
-- ---------------------------------------------------------------------

create policy "alerts_select_anon" on alerts
    for select
    to anon
    using (true);

create policy "alerts_select_authenticated" on alerts
    for select
    to authenticated
    using (true);

revoke insert, update, delete on alerts from anon;

-- Any authenticated user may acknowledge any alert (no per-user
-- ownership on alerts), but only these four columns. The policy's
-- using/with check are both `true` on purpose -- the real restriction is
-- the column grant just below, which the row policy alone cannot express.
create policy "alerts_ack_update_authenticated" on alerts
    for update
    to authenticated
    using (true)
    with check (true);

revoke update on alerts from authenticated;
grant update (ack_ts, driver_cause, action_taken, outcome) on alerts to authenticated;
revoke insert, delete on alerts from authenticated;

-- ---------------------------------------------------------------------
-- profiles: a user reads and writes only their own row. No anon access
-- at all -- there is nothing for an unauthenticated visitor to do here.
-- ---------------------------------------------------------------------

create policy "profiles_select_own" on profiles
    for select
    to authenticated
    using (id = auth.uid());

create policy "profiles_insert_own" on profiles
    for insert
    to authenticated
    with check (id = auth.uid());

create policy "profiles_update_own" on profiles
    for update
    to authenticated
    using (id = auth.uid())
    with check (id = auth.uid());

revoke all on profiles from anon;
revoke delete on profiles from authenticated;

-- ---------------------------------------------------------------------
-- The service role bypasses RLS entirely (Supabase's own design), so no
-- policy is needed to let local ingest INSERT telemetry/alerts -- holding
-- SUPABASE_SERVICE_KEY is what grants that, and that key must never reach
-- the frontend build (see README).
-- ---------------------------------------------------------------------
