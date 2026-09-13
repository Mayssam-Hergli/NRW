import { useEffect, useRef, useState } from "react";
import { supabase } from "../lib/supabase";
import type { TelemetryPacket, TelemetryRow } from "../lib/types";

export type ConnectionState = "connecting" | "connected" | "disconnected";

const HISTORY_LIMIT = 240; // 4h at 60s cadence -- enough for a readable curve

/** Fetches recent history immediately (so the view renders without waiting
 * on the next live packet -- the database is seeded with completed
 * shipments, so there's always something to show), then subscribes to new
 * inserts for this device. Reconnects and refetches on drop rather than
 * silently going stale. */
export function useTelemetryHistory(deviceId: string | null) {
  const [packets, setPackets] = useState<TelemetryPacket[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [error, setError] = useState<string | null>(null);
  const seqSeen = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!deviceId) {
      setPackets([]);
      return;
    }

    let cancelled = false;
    seqSeen.current = new Set();

    async function fetchHistory() {
      const { data, error: fetchError } = await supabase
        .from("telemetry")
        .select("payload")
        .eq("device_id", deviceId)
        .order("ts", { ascending: false })
        .limit(HISTORY_LIMIT);
      if (cancelled) return;
      if (fetchError) {
        setError(fetchError.message);
        return;
      }
      const rows = (data ?? []) as Pick<TelemetryRow, "payload">[];
      const ordered = rows.map((r) => r.payload).reverse();
      seqSeen.current = new Set(ordered.map((p) => p.seq));
      setPackets(ordered);
      setError(null);
    }

    function addPacket(packet: TelemetryPacket) {
      if (seqSeen.current.has(packet.seq)) return;
      seqSeen.current.add(packet.seq);
      setPackets((prev) => [...prev.slice(-HISTORY_LIMIT + 1), packet]);
    }

    let channel = supabase.channel(`telemetry:${deviceId}`);

    function connect() {
      channel = supabase.channel(`telemetry:${deviceId}:${Date.now()}`);
      channel
        .on(
          "postgres_changes",
          { event: "INSERT", schema: "public", table: "telemetry", filter: `device_id=eq.${deviceId}` },
          (payload) => addPacket((payload.new as TelemetryRow).payload),
        )
        .subscribe((status) => {
          if (cancelled) return;
          if (status === "SUBSCRIBED") {
            setConnection("connected");
          } else if (status === "CLOSED" || status === "TIMED_OUT" || status === "CHANNEL_ERROR") {
            setConnection("disconnected");
            // Reconnect and refetch rather than going stale: a gap may
            // have opened while the socket was down.
            supabase.removeChannel(channel);
            setTimeout(() => {
              if (!cancelled) {
                fetchHistory();
                connect();
              }
            }, 1500);
          } else {
            setConnection("connecting");
          }
        });
    }

    fetchHistory();
    connect();

    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, [deviceId]);

  return { packets, connection, error };
}
