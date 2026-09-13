import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { FleetEntry } from "../hooks/useFleet";
import { FleetInsights } from "./FleetInsights";

describe("fleet decision indicators", () => {
  it("counts a cold probe excursion, ignores external probes, and distinguishes stale telemetry", () => {
    const entries = [
      { latest: { ts: new Date(Date.now() - 600000).toISOString(), band: { min_c: 2, max_c: 8 }, cargo: [{ pos: "front", t_c: 1 }, { pos: "top", t_c: 5 }] }, activeAlerts: [{ ack_ts: null }, { ack_ts: "2026-01-01" }] },
      { latest: { ts: new Date().toISOString(), band: { min_c: 2, max_c: 8 }, cargo: [{ pos: "front", t_c: 4 }, { pos: "ambient_external", t_c: 30 }] }, activeAlerts: [] },
    ] as unknown as FleetEntry[];
    render(<FleetInsights entries={entries} locale="en" />);
    for (const label of ["Vehicles outside band", "No recent reading", "Alerts awaiting acknowledgment"]) {
      expect(screen.getByText(label).parentElement).toHaveTextContent("1");
    }
    expect(screen.getByText("Observed vehicles").parentElement).toHaveTextContent("2");
  });
});
