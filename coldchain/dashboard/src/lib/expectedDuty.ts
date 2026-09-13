// Ported from simulator/electrical.py::ElectricalSim.expected_duty_pct and
// simulator/thermal.py::stationary_capacity_frac (constants from
// simulator/config.py). Not imported -- those live outside shared/, so
// there is no frozen contract guaranteeing they stay put, and a static
// site can't import server-side Python anyway. This is the same formula
// models/electrical_health.py (M2) evaluates against, called the same way
// (raw packet.ambient_c stands in for "effective ambient", exactly as
// M2's own tests call it) -- so this chart shows the same signal M2 would
// alert on, not an approximation of it.
//
// This is the client-side computation that makes the dispatcher's
// "duty_pct vs expected_duty_pct" chart possible at all: expected_duty_pct
// is a derived quantity, not a field on TelemetryPacket, and nothing in
// this repo yet writes it out per-packet to a live table.

const THERMAL_TAU_MIN = 120.0;
const COOLING_POWER_C_PER_MIN = 0.55;
const STATIONARY_SPEED_THRESHOLD_KMH = 2.0;
const CAPACITY_DEGRADE_AMBIENT_BASELINE_C = 25.0;
const CAPACITY_DEGRADE_PER_C = 0.02;
const MIN_STATIONARY_CAPACITY_FRAC = 0.5;

export function stationaryCapacityFrac(speedKmh: number, ambientC: number): number {
  if (speedKmh > STATIONARY_SPEED_THRESHOLD_KMH) {
    return 1.0;
  }
  const excessC = Math.max(0.0, ambientC - CAPACITY_DEGRADE_AMBIENT_BASELINE_C);
  const frac = 1.0 - CAPACITY_DEGRADE_PER_C * excessC;
  return Math.max(MIN_STATIONARY_CAPACITY_FRAC, frac);
}

/** ambientC stands in for effective ambient -- see module docstring. */
export function expectedDutyPct(ambientC: number, speedKmh: number, setpointC: number): number {
  const capacityFrac = stationaryCapacityFrac(speedKmh, ambientC);
  const gapC = Math.max(0.0, ambientC - setpointC);
  if (gapC <= 0.0) {
    return 0.0;
  }
  const denom = THERMAL_TAU_MIN * COOLING_POWER_C_PER_MIN * capacityFrac;
  const dutyFrac = gapC / denom;
  return Math.max(0.0, Math.min(100.0, dutyFrac * 100.0));
}
