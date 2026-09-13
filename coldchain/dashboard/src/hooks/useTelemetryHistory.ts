import { useCallback, useMemo } from "react";
import { supabase } from "../lib/supabase";
import { packetOrder, readPages } from "../lib/liveData";
import type { TelemetryRow } from "../lib/types";
import { useLiveRows } from "./useLiveRows";

export type ConnectionState = "connecting" | "connected" | "disconnected";
const rowKey = (row: TelemetryRow) => String(row.id);

export function useTelemetryHistory(deviceId: string | null) {
  const fetchRows = useCallback(() => readPages<TelemetryRow>((from, to) => supabase.from("telemetry").select("*").eq("device_id", deviceId!).order("ts", { ascending: false }).order("id", { ascending: false }).range(from, to), 1440), [deviceId]);
  const { rows, ...state } = useLiveRows({ scope: `telemetry:${deviceId}`, table: "telemetry", filter: deviceId ? `device_id=eq.${deviceId}` : undefined, enabled: !!deviceId, fetchRows, key: rowKey });
  const packets = useMemo(() => rows.filter(r => r.device_id === deviceId).map(r => r.payload).sort(packetOrder).slice(-1440), [rows, deviceId]);
  return { packets, ...state };
}
