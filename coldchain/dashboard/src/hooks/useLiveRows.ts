import { useEffect, useRef, useState } from "react";
import { supabase } from "../lib/supabase";
import type { RealtimeChannel } from "@supabase/supabase-js";

export type ConnectionState = "connecting" | "connected" | "disconnected";

interface UseLiveRowsOptions<T> {
  /** Unique per distinct subscription (e.g. `telemetry:${deviceId}`) --
   * used to key the realtime channel name and to reset state when the
   * underlying query target changes. */
  scope: string;
  table: string;
  fetchRows: () => Promise<{ data: T[]; truncated: boolean }>;
  key: (row: T) => string;
  filter?: string;
  enabled?: boolean;
}

/** The fetch-then-subscribe-with-reconnect pattern every data hook in this
 * app needs (useFleet, useTelemetryHistory, useAlerts, useShipments),
 * pulled out once: fetch recent rows immediately so the view renders
 * without waiting on the next live packet, then subscribe to
 * inserts/updates on `table`, upserting by `key`. Reconnects and refetches
 * on drop rather than silently going stale. */
export function useLiveRows<T>({ scope, table, fetchRows, key, filter, enabled = true }: UseLiveRowsOptions<T>) {
  const [rows, setRows] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const rowsByKey = useRef<Map<string, T>>(new Map());
  const retryToken = useRef(0);

  useEffect(() => {
    if (!enabled) {
      setRows([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    rowsByKey.current = new Map();

    function publish() {
      setRows(Array.from(rowsByKey.current.values()));
    }

    async function fetchInitial() {
      setLoading(true);
      try {
        const { data, truncated: wasTruncated } = await fetchRows();
        if (cancelled) return;
        rowsByKey.current = new Map(data.map((row) => [key(row), row]));
        setTruncated(wasTruncated);
        setError(null);
        publish();
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    function upsert(row: T) {
      rowsByKey.current.set(key(row), row);
      publish();
    }

    let channel: RealtimeChannel;

    function connect() {
      channel = supabase.channel(`${scope}:${Date.now()}`);
      channel
        .on(
          "postgres_changes",
          { event: "INSERT", schema: "public", table, filter },
          (payload) => upsert(payload.new as T),
        )
        .on(
          "postgres_changes",
          { event: "UPDATE", schema: "public", table, filter },
          (payload) => upsert(payload.new as T),
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
    // retryToken.current is bumped by retry() below to force this effect
    // to re-run without needing scope/filter/enabled themselves to change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, table, filter, enabled, retryToken.current]);

  function retry() {
    retryToken.current += 1;
    setConnection("connecting");
  }

  return { rows, loading, error, truncated, connection, retry };
}
