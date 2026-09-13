import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import type { MissionProfile, TelemetryPacket, TelemetryRow } from "../lib/types";
import type { ConnectionState } from "./useTelemetryHistory";

export interface Shipment {
  shipmentId: string;
  deviceId: string;
  profile: MissionProfile | null;
  packets: TelemetryPacket[];
}

const FETCH_LIMIT = 3000;

type TelemetryRowForGrouping = Pick<TelemetryRow, "device_id" | "shipment_id" | "seq" | "payload">;

/** All shipments with telemetry, grouped client-side (no shipments table
 * exists yet -- shipment_id lives only as a column/payload field on
 * telemetry rows). Live: fetches recent history, then keeps every
 * shipment's packet list current via realtime inserts. */
export function useShipments() {
  const [shipments, setShipments] = useState<Map<string, Shipment>>(new Map());
  const [connection, setConnection] = useState<ConnectionState>("connecting");

  useEffect(() => {
    let cancelled = false;

    function groupInto(map: Map<string, Shipment>, row: TelemetryRowForGrouping) {
      const shipmentId = row.shipment_id;
      if (!shipmentId) return;
      const existing = map.get(shipmentId);
      if (existing) {
        if (!existing.packets.some((p) => p.seq === row.payload.seq)) {
          existing.packets.push(row.payload);
        }
      } else {
        map.set(shipmentId, {
          shipmentId,
          deviceId: row.device_id,
          profile: row.payload.mission_profile,
          packets: [row.payload],
        });
      }
    }

    async function fetchAll() {
      const { data, error } = await supabase
        .from("telemetry")
        .select("device_id, shipment_id, seq, payload")
        .not("shipment_id", "is", null)
        .order("ts", { ascending: true })
        .limit(FETCH_LIMIT);
      if (cancelled || error) return;
      const next = new Map<string, Shipment>();
      for (const row of (data ?? []) as TelemetryRowForGrouping[]) {
        groupInto(next, row);
      }
      setShipments(next);
    }

    let channel = supabase.channel("shipments");

    function connect() {
      channel = supabase.channel(`shipments:${Date.now()}`);
      channel
        .on("postgres_changes", { event: "INSERT", schema: "public", table: "telemetry" }, (payload) => {
          const row = payload.new as TelemetryRow;
          if (!row.shipment_id) return;
          setShipments((prev) => {
            const next = new Map(prev);
            groupInto(next, row);
            return next;
          });
        })
        .subscribe((status) => {
          if (cancelled) return;
          if (status === "SUBSCRIBED") {
            setConnection("connected");
          } else if (status === "CLOSED" || status === "TIMED_OUT" || status === "CHANNEL_ERROR") {
            setConnection("disconnected");
            supabase.removeChannel(channel);
            setTimeout(() => {
              if (!cancelled) {
                fetchAll();
                connect();
              }
            }, 1500);
          } else {
            setConnection("connecting");
          }
        });
    }

    fetchAll();
    connect();

    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, []);

  return { shipments: Array.from(shipments.values()), connection };
}
