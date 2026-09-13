// Typed wrapper around src/generated/profiles.json (generated from
// shared/profiles.py by scripts/export_profiles.py). Same pattern as
// i18n/messages.ts: this file carries the type shape only, the data
// always comes from the generated JSON, never hand-copied.
import raw from "../generated/profiles.json";
import type { MissionProfile } from "./types";

export interface ProfileSpec {
  label: string;
  minC: number;
  maxC: number;
  freezeAlarm: boolean;
  cumulativeExcursionLimitMin: number;
  maxLuxHours: number | null;
  maxShockG: number;
  doorDwellLimitMin: number;
}

export const PROFILES = raw as unknown as Record<MissionProfile, ProfileSpec>;

export function getProfile(profile: MissionProfile): ProfileSpec {
  return PROFILES[profile];
}
