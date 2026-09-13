import { useEffect, useRef, useState } from "react";
import { supabase } from "../lib/supabase";
import type { AlertRow, TelemetryPacket, TelemetryRow } from "../lib/types";
import type { ConnectionState } from "./useTelemetryHistory";

export interface FleetEntry {
  deviceId: string;
  latest: TelemetryPacket;
  activeAlerts: AlertRow[];
}

const ACTIVE_ALERT_STATES = new Set(["watch", "warning", "critical", "escalated"]);

function severityRank(entry: FleetEntry): number {
  if (entry.activeAlerts.some((a) => a.severity === "critical")) return 3;
  if (entry.activeAlerts.some((a) => a.severity === "warning")) return 2;
  if (entry.activeAlerts.some((a) => a.severity === "watch")) return 1;
  return 0;
}

/** Fleet-wide view for the dispatcher: latest packet per device, plus
 * whichever alerts are still active, sorted worst-first. */
export function useFleet() {
  const [byDevice, setByDevice] = useState<Map<string, FleetEntry>>(new Map());
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const latestSeq = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    let cancelled = false;

    async function fetchInitial() {
      // Most recent packet per device: pull a generous recent window and
      // reduce client-side rather than relying on a DB-side DISTINCT ON,
      // to keep this working against plain PostgREST without a custom RPC.
      const { data: telemetryRows } = await supabase
        .from("telemetry")
        .select("device_id, seq, payload")
        .order("ts", { ascending: false })
        .limit(500);

      const latestByDevice = new Map<string, TelemetryPacket>();
      for (const row of (telemetryRows ?? []) as Pick<TelemetryRow, "device_id" | "seq" | "payload">[]) {
        if (!latestByDevice.has(row.device_id)) {
          latestByDevice.set(row.device_id, row.payload);
          latestSeq.current.set(row.device_id, row.seq);
        }
      }

      const { data: alertRows } = await supabase
        .from("alerts")
        .select("*")
        .in("state", Array.from(ACTIVE_ALERT_STATES))
        .order("issued_ts", { ascending: false });

      const alertsByDevice = new Map<string, AlertRow[]>();
      for (const alert of (alertRows ?? []) as AlertRow[]) {
        const list = alertsByDevice.get(alert.device_id) ?? [];
        list.push(alert);
        alertsByDevice.set(alert.device_id, list);
      }

      if (cancelled) return;
      const next = new Map<string, FleetEntry>();
      for (const [deviceId, latest] of latestByDevice) {
        next.set(deviceId, { deviceId, latest, activeAlerts: alertsByDevice.get(deviceId) ?? [] });
      }
      setByDevice(next);
    }

    let channel = supabase.channel("fleet");

    function connect() {
      channel = supabase.channel(`fleet:${Date.now()}`);
      channel
        .on("postgres_changes", { event: "INSERT", schema: "public", table: "telemetry" }, (payload) => {
          const row = payload.new as TelemetryRow;
          const seenSeq = latestSeq.current.get(row.device_id);
          if (seenSeq !== undefined && row.seq <= seenSeq) return;
          latestSeq.current.set(row.device_id, row.seq);
          setByDevice((prev) => {
            const next = new Map(prev);
            const existing = next.get(row.device_id);
            next.set(row.device_id, {
              deviceId: row.device_id,
              latest: row.payload,
              activeAlerts: existing?.activeAlerts ?? [],
            });
            return next;
          });
        })
        .on(
          "postgres_changes",
          { event: "*", schema: "public", table: "alerts" },
          (payload) => {
            const row = (payload.new ?? payload.old) as AlertRow;
            setByDevice((prev) => {
              const existing = prev.get(row.device_id);
              if (!existing) return prev;
              const withoutThis = existing.activeAlerts.filter((a) => a.alert_id !== row.alert_id);
              const stillActive = ACTIVE_ALERT_STATES.has((payload.new as AlertRow | null)?.state ?? "");
              const nextAlerts = stillActive ? [...withoutThis, payload.new as AlertRow] : withoutThis;
              const next = new Map(prev);
              next.set(row.device_id, { ...existing, activeAlerts: nextAlerts });
              return next;
            });
          },
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
                fetchInitial();
                connect();
              }
            }, 1500);
          } else {
            setConnection("connecting");
          }
        });
    }

    fetchInitial();
    connect();

    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, []);

  const entries = Array.from(byDevice.values()).sort((a, b) => severityRank(b) - severityRank(a));

  return { entries, connection };
}
