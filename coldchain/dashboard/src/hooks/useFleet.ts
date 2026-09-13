import { useMemo } from "react";
import { supabase } from "../lib/supabase";
import { packetOrder, readPages } from "../lib/liveData";
import type { AlertRow, TelemetryPacket, TelemetryRow } from "../lib/types";
import { useLiveRows } from "./useLiveRows";
import { useAlerts } from "./useAlerts";

export interface FleetEntry { deviceId: string; latest: TelemetryPacket; activeAlerts: AlertRow[] }
const active = new Set(["watch", "warning", "critical", "acknowledged", "escalated"]);
const rowKey = (row: TelemetryRow) => String(row.id);
const fetchRows = () => readPages<TelemetryRow>((from, to) => supabase.from("telemetry").select("*").order("ts", { ascending: false }).order("id", { ascending: false }).range(from, to));

export function useFleet() {
  const telemetry = useLiveRows({ scope: "fleet", table: "telemetry", fetchRows, key: rowKey });
  const alerts = useAlerts(null);
  const entries = useMemo(() => {
    const latest = new Map<string, TelemetryPacket>();
    for (const row of telemetry.rows) {
      const previous = latest.get(row.device_id);
      if (!previous || packetOrder(row.payload, previous) > 0) latest.set(row.device_id, row.payload);
    }
    return [...latest].map(([deviceId, packet]) => ({ deviceId, latest: packet, activeAlerts: alerts.alerts.filter(a => a.device_id === deviceId && active.has(a.state)) })).sort((a, b) => a.deviceId.localeCompare(b.deviceId));
  }, [telemetry.rows, alerts.alerts]);
  return { entries, loading: telemetry.loading || alerts.loading, error: telemetry.error ?? alerts.error, truncated: telemetry.truncated || alerts.truncated,
    connection: telemetry.connection === "disconnected" || alerts.connection === "disconnected" ? "disconnected" as const : telemetry.connection === "connected" && alerts.connection === "connected" ? "connected" as const : "connecting" as const,
    retry: () => { telemetry.retry(); alerts.retry(); } };
}
