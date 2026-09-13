// Shared helpers behind every data hook (useFleet, useTelemetryHistory,
// useAlerts, useShipments): pagination past PostgREST's per-request row
// cap, and a consistent chronological ordering for TelemetryPackets.
import type { TelemetryPacket } from "./types";

const PAGE_SIZE = 1000;

interface PageResult<T> {
  data: T[] | null;
  error: { message: string } | null;
}

/** Repeatedly calls queryPage(from, to) until a page comes back short (the
 * query is exhausted) or maxRows is reached. Supabase/PostgREST caps a
 * single request's rows (1000 by default) -- this is what lets a hook ask
 * for "all of it" without silently dropping anything past that cap, while
 * still bounding how much a single device/shipment can pull in. */
export async function readPages<T>(
  queryPage: (from: number, to: number) => PromiseLike<PageResult<T>>,
  maxRows: number = 10000,
): Promise<{ data: T[]; truncated: boolean }> {
  const all: T[] = [];
  let from = 0;

  while (all.length < maxRows) {
    const to = Math.min(from + PAGE_SIZE, maxRows) - 1;
    const { data, error } = await queryPage(from, to);
    if (error) {
      throw new Error(error.message);
    }
    if (!data || data.length === 0) {
      break;
    }
    all.push(...data);
    if (data.length < to - from + 1) {
      // Fewer rows than asked for means the query is exhausted.
      break;
    }
    from += PAGE_SIZE;
  }

  const truncated = all.length >= maxRows;
  return { data: truncated ? all.slice(0, maxRows) : all, truncated };
}

/** Chronological order for TelemetryPackets: ts first, seq as a tie-break
 * for same-timestamp packets (buffered replays can share a timestamp down
 * to the second). Positive means `a` is newer than `b`, matching Array.sort
 * and the ">" comparisons call sites use directly. */
export function packetOrder(a: TelemetryPacket, b: TelemetryPacket): number {
  const byTs = Date.parse(a.ts) - Date.parse(b.ts);
  if (byTs !== 0) return byTs;
  return a.seq - b.seq;
}
