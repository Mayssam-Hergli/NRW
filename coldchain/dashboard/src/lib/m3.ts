// Ported from models/m3_mkt.py -- not imported (that's server-side Python;
// this is a static site), so faithfully mirrored instead. Same reasoning
// as expectedDuty.ts: nothing in this repo yet writes MKT/verdict per
// shipment into a live table, so the quality view has to derive it from
// raw telemetry itself using the exact same formula M3 does.

import type { MissionProfile, TelemetryPacket } from "./types";

const R_KJ_PER_MOL_K = 8.314462618e-3;

// USP <1150>'s conventional default activation energy for MKT.
export const DEFAULT_ACTIVATION_ENERGY_KJ_MOL = 83.144;

// A reading more than this many minutes from the next is a genuine,
// unobserved gap, not just slow cadence -- see models/m3_mkt.py's own
// docstring for the reasoning.
export const GAP_THRESHOLD_MIN = 15.0;

// Illustrative reference shelf life at each profile's labelled storage
// temperature, in days -- demonstration assumptions, not sourced from any
// real product's stability filing (see models/m3_mkt.py).
export const REFERENCE_SHELF_LIFE_DAYS: Record<MissionProfile, number> = {
  pharma_refrigerated: 730.0,
  pharma_frozen: 1095.0,
  controlled_room_temp: 1095.0,
  vaccines: 365.0,
  fresh_produce: 14.0,
};

export const MIN_COVERAGE_PCT_FOR_COMPLIANT = 98.0;

export type Verdict = "compliant" | "minor_deviation" | "excursion_review";

export interface BudgetResult {
  mktC: number;
  pctConsumed: number;
  minutesOutOfBandAbove: number;
  minutesOutOfBandBelow: number;
  worstExcursionC: number | null;
  worstExcursionDurationMin: number;
  coveragePct: number;
  verdict: Verdict;
}

export interface Reading {
  ts: Date;
  tempC: number;
}

function celsiusToKelvin(c: number): number {
  return c + 273.15;
}

function sortedDistinct(readings: Reading[]): Reading[] {
  if (readings.length === 0) {
    throw new Error("at least one reading is required");
  }
  return [...readings].sort((a, b) => a.ts.getTime() - b.ts.getTime());
}

/** (reading, minutes-until-next) for every reading whose gap to the next
 * is within GAP_THRESHOLD_MIN. The last reading is never included. */
function validIntervals(ordered: Reading[]): Array<{ reading: Reading; weightMin: number }> {
  const out: Array<{ reading: Reading; weightMin: number }> = [];
  for (let i = 0; i < ordered.length - 1; i++) {
    const gapMin = (ordered[i + 1].ts.getTime() - ordered[i].ts.getTime()) / 60000;
    if (gapMin <= GAP_THRESHOLD_MIN) {
      out.push({ reading: ordered[i], weightMin: gapMin });
    }
  }
  return out;
}

export function meanKineticTemperature(
  readings: Reading[],
  activationEnergyKjMol: number = DEFAULT_ACTIVATION_ENERGY_KJ_MOL,
): number {
  const ordered = sortedDistinct(readings);
  if (ordered.length === 1) {
    return ordered[0].tempC;
  }

  const ea = activationEnergyKjMol;
  let numerator = 0;
  let denominator = 0;
  for (const { reading, weightMin } of validIntervals(ordered)) {
    const tK = celsiusToKelvin(reading.tempC);
    numerator += weightMin * Math.exp(-ea / (R_KJ_PER_MOL_K * tK));
    denominator += weightMin;
  }

  let jAvg: number;
  if (denominator <= 0) {
    const js = ordered.map((r) => Math.exp(-ea / (R_KJ_PER_MOL_K * celsiusToKelvin(r.tempC))));
    jAvg = js.reduce((a, b) => a + b, 0) / js.length;
  } else {
    jAvg = numerator / denominator;
  }

  return -ea / (R_KJ_PER_MOL_K * Math.log(jAvg)) - 273.15;
}

export interface ProfileBandSpec {
  minC: number;
  maxC: number;
  freezeAlarm: boolean;
  cumulativeExcursionLimitMin: number;
}

export function stabilityBudgetConsumed(
  readings: Reading[],
  profile: MissionProfile,
  spec: ProfileBandSpec,
  shipmentDurationMin: number,
  activationEnergyKjMol: number = DEFAULT_ACTIVATION_ENERGY_KJ_MOL,
): BudgetResult {
  const ordered = sortedDistinct(readings);
  const mktC = meanKineticTemperature(readings, activationEnergyKjMol);

  const tRefK = celsiusToKelvin((spec.minC + spec.maxC) / 2.0);
  const tMktK = celsiusToKelvin(mktC);
  const rateRatio = Math.exp(
    (activationEnergyKjMol / R_KJ_PER_MOL_K) * (1.0 / tRefK - 1.0 / tMktK),
  );
  const shipmentDurationDays = shipmentDurationMin / (60.0 * 24.0);
  const referenceShelfLifeDays = REFERENCE_SHELF_LIFE_DAYS[profile];
  const pctConsumed = (100.0 * shipmentDurationDays * rateRatio) / referenceShelfLifeDays;

  let minutesAbove = 0;
  let minutesBelow = 0;
  let observedMin = 0;
  const runs: Array<{ duration: number; peakC: number; peakDeviation: number }> = [];
  let current: { duration: number; peakC: number; peakDeviation: number } | null = null;

  for (const { reading, weightMin } of validIntervals(ordered)) {
    observedMin += weightMin;
    let deviation: number | null = null;
    if (reading.tempC > spec.maxC) {
      minutesAbove += weightMin;
      deviation = reading.tempC - spec.maxC;
    } else if (reading.tempC < spec.minC) {
      minutesBelow += weightMin;
      deviation = spec.minC - reading.tempC;
    }

    if (deviation !== null) {
      if (current !== null) {
        current.duration += weightMin;
        if (deviation > current.peakDeviation) {
          current.peakDeviation = deviation;
          current.peakC = reading.tempC;
        }
      } else {
        current = { duration: weightMin, peakC: reading.tempC, peakDeviation: deviation };
      }
    } else if (current !== null) {
      runs.push(current);
      current = null;
    }
  }
  if (current !== null) {
    runs.push(current);
  }

  const coveragePct =
    shipmentDurationMin > 0 ? Math.min(100.0, (100.0 * observedMin) / shipmentDurationMin) : 0.0;

  const worst = runs.reduce<(typeof runs)[number] | null>(
    (best, r) => (best === null || r.peakDeviation > best.peakDeviation ? r : best),
    null,
  );
  const worstExcursionC = worst?.peakC ?? null;
  const worstExcursionDurationMin = worst?.duration ?? 0;

  const totalOutOfBand = minutesAbove + minutesBelow;
  const freezeBreach = spec.freezeAlarm && minutesBelow > 0.0;

  let verdict: Verdict;
  if (freezeBreach) {
    verdict = "excursion_review";
  } else if (coveragePct < MIN_COVERAGE_PCT_FOR_COMPLIANT) {
    verdict = "excursion_review";
  } else if (totalOutOfBand <= 0.0) {
    verdict = "compliant";
  } else if (totalOutOfBand <= spec.cumulativeExcursionLimitMin) {
    verdict = "minor_deviation";
  } else {
    verdict = "excursion_review";
  }

  return {
    mktC,
    pctConsumed,
    minutesOutOfBandAbove: minutesAbove,
    minutesOutOfBandBelow: minutesBelow,
    worstExcursionC,
    worstExcursionDurationMin,
    coveragePct,
    verdict,
  };
}

/** Buffered packets are excluded by default -- see models/m3_mkt.py's
 * readings_from_packets docstring: a delayed recovery is not the same as
 * a live reading for compliance purposes. */
export function readingsFromPackets(
  packets: TelemetryPacket[],
  aggregate: (values: number[]) => number = (values) => Math.max(...values),
  excludeBuffered = true,
): Reading[] {
  const out: Reading[] = [];
  for (const packet of packets) {
    if (excludeBuffered && packet.buffered) continue;
    const cargoTemps = packet.cargo.filter((c) => c.pos !== "ambient_external").map((c) => c.t_c);
    if (cargoTemps.length === 0) continue;
    out.push({ ts: new Date(packet.ts), tempC: aggregate(cargoTemps) });
  }
  return out;
}
