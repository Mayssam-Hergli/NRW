import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import type { AlertRow, DriverCause, Outcome } from "../lib/types";
import type { ConnectionState } from "./useTelemetryHistory";

/** Alerts for one device (driver view) or the whole fleet (dispatcher
 * register) when deviceId is null. Fetches recent history first, then
 * subscribes to inserts/updates; reconnects and refetches on drop. */
export function useAlerts(deviceId: string | null) {
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [writeError, setWriteError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchRecent() {
      let query = supabase.from("alerts").select("*").order("issued_ts", { ascending: false }).limit(100);
      if (deviceId) {
        query = query.eq("device_id", deviceId);
      }
      const { data, error } = await query;
      if (cancelled) return;
      if (!error) {
        setAlerts((data ?? []) as AlertRow[]);
      }
    }

    function upsert(row: AlertRow) {
      setAlerts((prev) => {
        const idx = prev.findIndex((a) => a.alert_id === row.alert_id);
        if (idx === -1) return [row, ...prev];
        const next = [...prev];
        next[idx] = row;
        return next;
      });
    }

    let channel = supabase.channel(`alerts:${deviceId ?? "all"}`);

    function connect() {
      const filter = deviceId ? `device_id=eq.${deviceId}` : undefined;
      channel = supabase.channel(`alerts:${deviceId ?? "all"}:${Date.now()}`);
      channel
        .on(
          "postgres_changes",
          { event: "INSERT", schema: "public", table: "alerts", filter },
          (payload) => upsert(payload.new as AlertRow),
        )
        .on(
          "postgres_changes",
          { event: "UPDATE", schema: "public", table: "alerts", filter },
          (payload) => upsert(payload.new as AlertRow),
        )
        .subscribe((status) => {
          if (cancelled) return;
          if (status === "SUBSCRIBED") {
            setConnection("connected");
          } else if (status === "CLOSED" || status === "TIMED_OUT" || status === "CHANNEL_ERROR") {
            setConnection("disconnected");
            supabase.removeChannel(channel);
            setTimeout(() => {
              if (!cancelled) {
                fetchRecent();
                connect();
              }
            }, 1500);
          } else {
            setConnection("connecting");
          }
        });
    }

    fetchRecent();
    connect();

    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, [deviceId]);

  /** RLS (infra/rls.sql) grants UPDATE on exactly these four columns to
   * any authenticated user -- attempt no other write. If Postgres rejects
   * it, surface the error rather than failing silently. */
  async function acknowledge(
    alertId: string,
    fields: { driverCause?: DriverCause; actionTaken?: string; outcome?: Outcome },
  ) {
    const { error } = await supabase
      .from("alerts")
      .update({
        ack_ts: new Date().toISOString(),
        driver_cause: fields.driverCause ?? null,
        action_taken: fields.actionTaken ?? null,
        outcome: fields.outcome ?? "pending",
      })
      .eq("alert_id", alertId);
    if (error) {
      setWriteError(error.message);
      throw error;
    }
    setWriteError(null);
  }

  return { alerts, connection, acknowledge, writeError };
}
