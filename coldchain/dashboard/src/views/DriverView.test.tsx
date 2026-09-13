import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AlertRow, TelemetryPacket, UserProfile } from "../lib/types";
import { DriverView } from "./DriverView";

const baseProfile: UserProfile = {
  id: "user-1",
  role: "driver",
  locale: "fr",
  display_name: "Test Driver",
  created_at: new Date().toISOString(),
};

function makePacket(speedKmh: number): TelemetryPacket {
  return {
    device_id: "TN-1234-GW",
    shipment_id: "SHIP-1",
    mission_profile: "pharma_refrigerated",
    band: { min_c: 2.0, max_c: 8.0 },
    ts: new Date(Date.now() - mockAge).toISOString(),
    seq: 1,
    buffered: false,
    gnss: { lat: 36.8, lon: 10.18, speed_kmh: speedKmh, fix: "3D" },
    cargo: [{ tag: "P1", pos: "front", t_c: mockTemp, rh: null }],
    ambient_c: 30.0,
    door: { open: false, events: 0 },
    light_lux: 0,
    motion: { peak_g: 0.1, shock_events: 0, vib_rms: 0.01 },
    power: {
      v_bus: 24.0,
      compressor: { i_rms: 4.0, inrush_peak: null, duty_pct: 40.0 },
      cond_fan: { i_rms: 0.9, inrush_peak: null, duty_pct: null },
      evap_fan: { i_rms: 0.7, inrush_peak: null, duty_pct: null },
      state: "RUN",
    },
    health: { batt_v: 12.6, rssi: -70, buffer_pct: 0, gnss_fix: "3D" },
    sig: null,
  };
}

function makeAlert(): AlertRow {
  const message = "Froid affaibli. Dépassement dans 38 min.";
  return {
    alert_id: "alert-1",
    device_id: "TN-1234-GW",
    shipment_id: "SHIP-1",
    issued_ts: new Date().toISOString(),
    state: "warning",
    severity: "critical",
    cause: "refrigerant_loss",
    payload: {
      alert_id: "alert-1",
      device_id: "TN-1234-GW",
      shipment_id: "SHIP-1",
      issued_ts: new Date().toISOString(),
      tier: 1,
      state: "warning",
      severity: "critical",
      cause: "refrigerant_loss",
      evidence: { dev_pp: 22 },
      predicted_breach_min: 38,
      prescribed_action: "schedule_service",
      message,
      ack_ts: null,
      driver_cause: null,
      action_taken: null,
      outcome: "pending",
      delivered_offline: false,
      escalated_ts: null,
      resolved_ts: null,
    },
    ack_ts: null,
    driver_cause: null,
    action_taken: null,
    outcome: "pending",
  };
}

let mockSpeed = 0;
let mockAge = 0;
let mockTemp = 5;
let mockHasAlert = true;
const mockSignOut = vi.fn().mockResolvedValue(undefined);
beforeEach(() => { mockSpeed = 0; mockAge = 0; mockTemp = 5; mockHasAlert = true; });

vi.mock("../lib/auth", () => ({
  useAuth: () => ({ profile: baseProfile, activeView: "driver", setActiveView: vi.fn(), signOut: mockSignOut }),
}));

vi.mock("../hooks/useFleet", () => ({
  useFleet: () => ({
    entries: [{ deviceId: "TN-1234-GW", latest: makePacket(mockSpeed), activeAlerts: [] }],
    connection: "connected",
  }),
}));

vi.mock("../hooks/useTelemetryHistory", () => ({
  useTelemetryHistory: () => ({ packets: [makePacket(mockSpeed)], connection: "connected", error: null }),
}));

vi.mock("../hooks/useAlerts", () => ({
  useAlerts: () => ({ alerts: mockHasAlert ? [makeAlert()] : [], acknowledge: vi.fn(), writeError: null }),
}));

describe("DriverView speed gating", () => {
  it("allows logout while the driving layout is active", async () => {
    mockSpeed = 80;
    render(<DriverView locale="en" />);
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    await waitFor(() => expect(mockSignOut).toHaveBeenCalled());
  });
  it("does not reassure a moving driver when telemetry is stale", () => {
    mockSpeed = 80; mockAge = 600000; mockHasAlert = false;
    render(<DriverView locale="en" />);
    expect(screen.getAllByText(/Readings are stale/).length).toBeGreaterThan(0);
    expect(screen.queryByText("Everything's fine.")).not.toBeInTheDocument();
  });
  it("shows a low temperature excursion without requiring an alert", () => {
    mockTemp = 1; mockSpeed = 80; mockHasAlert = false;
    render(<DriverView locale="en" />);
    expect(screen.getByText("Temperature outside band")).toBeInTheDocument();
  });
  it("renders the same alert differently at 0 km/h vs 80 km/h", () => {
    mockSpeed = 0;
    const { container: stationary, unmount } = render(<DriverView locale="fr" />);
    const stationaryHtml = stationary.innerHTML;
    unmount();

    mockSpeed = 80;
    const { container: moving } = render(<DriverView locale="fr" />);
    const movingHtml = moving.innerHTML;

    expect(stationaryHtml).not.toEqual(movingHtml);
  });

  it("stationary view shows full detail (band indicator, cause picker)", () => {
    mockSpeed = 0;
    render(<DriverView locale="fr" />);
    // Stationary renders BandIndicator's band edges.
    expect(screen.getByText("2.0°C")).toBeInTheDocument();
    expect(screen.getByText("8.0°C")).toBeInTheDocument();
  });

  it("moving + critical severity shows the fixed pull-over instruction, not the cause-specific message", () => {
    mockSpeed = 80;
    render(<DriverView locale="fr" />);
    expect(screen.getByText("Arrêtez-vous en sécurité, puis vérifiez.")).toBeInTheDocument();
  });
});
