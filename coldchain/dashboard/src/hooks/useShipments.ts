import { useMemo } from "react";
import { supabase } from "../lib/supabase";
import { packetOrder, readPages } from "../lib/liveData";
import type { MissionProfile, TelemetryPacket, TelemetryRow } from "../lib/types";
import { useLiveRows } from "./useLiveRows";

export interface Shipment { shipmentId: string; deviceId: string; profile: MissionProfile | null; packets: TelemetryPacket[] }
const rowKey = (row: TelemetryRow) => String(row.id);
const fetchRows = () => readPages<TelemetryRow>((from, to) => supabase.from("telemetry").select("*").not("shipment_id", "is", null).order("ts", { ascending: false }).order("id", { ascending: false }).range(from, to));

export function useShipments() {
  const { rows, ...state } = useLiveRows({ scope: "shipments", table: "telemetry", fetchRows, key: rowKey });
  const shipments = useMemo(() => {
    const grouped = new Map<string, Shipment>();
    for (const row of rows) {
      if (!row.shipment_id) continue;
      let shipment = grouped.get(row.shipment_id);
      if (!shipment) { shipment = { shipmentId: row.shipment_id, deviceId: row.device_id, profile: row.payload.mission_profile, packets: [] }; grouped.set(row.shipment_id, shipment); }
      shipment.packets.push(row.payload);
    }
    for (const shipment of grouped.values()) shipment.packets.sort(packetOrder);
    return [...grouped.values()].sort((a, b) => Date.parse(b.packets.at(-1)!.ts) - Date.parse(a.packets.at(-1)!.ts));
  }, [rows]);
  return { shipments, ...state };
}
