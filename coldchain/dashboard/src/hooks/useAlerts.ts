import { useCallback, useMemo, useState } from "react";
import { supabase } from "../lib/supabase";
import { readPages } from "../lib/liveData";
import type { AlertRow, DriverCause, Outcome } from "../lib/types";
import { useLiveRows } from "./useLiveRows";

const rowKey = (row: AlertRow) => row.alert_id;
export function useAlerts(deviceId: string | null) {
  const [writeError, setWriteError] = useState<string | null>(null);
  const fetchRows = useCallback(() => readPages<AlertRow>((from, to) => {
    let query = supabase.from("alerts").select("*").order("issued_ts", { ascending: false }).order("alert_id");
    if (deviceId) query = query.eq("device_id", deviceId);
    return query.range(from, to);
  }, 5000), [deviceId]);
  const { rows, ...state } = useLiveRows({ scope: `alerts:${deviceId ?? "all"}`, table: "alerts", filter: deviceId ? `device_id=eq.${deviceId}` : undefined, fetchRows, key: rowKey });
  const alerts = useMemo(() => rows.filter(a => !deviceId || a.device_id === deviceId).sort((a, b) => Date.parse(b.issued_ts) - Date.parse(a.issued_ts)), [rows, deviceId]);
  async function acknowledge(alertId: string, fields: { driverCause?: DriverCause; actionTaken?: string; outcome?: Outcome }) {
    try {
      const current = await supabase.from("alerts").select("*").eq("alert_id", alertId).single();
      if (current.error) throw current.error;
      const previous = current.data as AlertRow;
      const result = await supabase.from("alerts").update({
        ack_ts: previous.ack_ts ?? new Date().toISOString(),
        ...(fields.driverCause !== undefined ? { driver_cause: fields.driverCause } : {}),
        ...(fields.actionTaken !== undefined ? { action_taken: fields.actionTaken } : {}),
        ...(fields.outcome !== undefined ? { outcome: fields.outcome } : {}),
      }).eq("alert_id", alertId).select("alert_id").single();
      if (result.error) throw result.error;
      setWriteError(null); state.retry();
    } catch (err) {
      setWriteError(err instanceof Error ? err.message : String((err as { message?: string }).message ?? err));
      throw err;
    }
  }
  return { alerts, ...state, acknowledge, writeError };
}
