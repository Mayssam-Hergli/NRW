// Isolates whether Realtime itself is working on the live project,
// bypassing React/DOM entirely: raw supabase-js subscription, print
// whatever arrives for 15s.
import { createClient } from "@supabase/supabase-js";

const url = process.env.VITE_SUPABASE_URL;
const anonKey = process.env.VITE_SUPABASE_ANON_KEY;
const supabase = createClient(url, anonKey);

const channel = supabase
  .channel("raw-test")
  .on("postgres_changes", { event: "INSERT", schema: "public", table: "telemetry" }, (payload) => {
    console.log("EVENT RECEIVED:", payload.new.device_id, payload.new.seq);
  })
  .subscribe((status, err) => {
    console.log("subscribe status:", status, err ?? "");
  });

console.log("Listening for 15s...");
await new Promise((resolve) => setTimeout(resolve, 15000));
await supabase.removeChannel(channel);
process.exit(0);
