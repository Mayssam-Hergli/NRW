// Mirrors shared/enums.py and shared/schema.py exactly -- these are the
// JSON shapes ingest/supabase_store.py writes into telemetry.payload and
// alerts.payload via Pydantic's `model_dump(mode="json")`. Field names,
// casing and enum string values must match the Python source verbatim;
// this file is hand-mirrored (not generated) because it's a static type
// shape, not string data -- unlike src/generated/messages.json, there's
// no per-build drift risk here, only a one-time-per-schema-change one.

export type MissionProfile =
  | "pharma_refrigerated"
  | "pharma_frozen"
  | "controlled_room_temp"
  | "vaccines"
  | "fresh_produce";

export type CompressorState = "RUN" | "OFF" | "SHORT_CYCLE" | "FAULT";

export type GnssFix = "NONE" | "2D" | "3D";

export type ProbePosition = "front" | "rear_door" | "top" | "bottom" | "ambient_external";

export type AlertState =
  | "nominal"
  | "suppressed"
  | "watch"
  | "warning"
  | "critical"
  | "escalated"
  | "acknowledged"
  | "resolved";

export type Severity = "watch" | "warning" | "critical";

export type FaultCause =
  | "bearing_wear"
  | "refrigerant_loss"
  | "short_cycling"
  | "fan_failure"
  | "voltage_sag"
  | "unit_off"
  | "offload_stop"
  | "door_unsecured"
  | "seal_failure"
  | "freeze_risk"
  | "shock_impact"
  | "light_exposure"
  | "tag_lost"
  | "ambient_strain"
  | "device_degraded";

export type PrescribedAction =
  | "close_door"
  | "secure_door"
  | "restart_unit"
  | "check_electrical"
  | "inspect_fan"
  | "inspect_seals"
  | "reposition_pallets"
  | "precool_now"
  | "raise_within_band"
  | "divert_cold_store"
  | "call_dispatch"
  | "schedule_service"
  | "pull_over_then_check"
  | "service_device";

export type DriverCause =
  | "offload_stop"
  | "door_left_open"
  | "unit_failure"
  | "power_issue"
  | "loading_delay"
  | "other";

export type Outcome = "pending" | "recovered" | "not_recovered";

export interface Band {
  min_c: number;
  max_c: number;
}

export interface Gnss {
  lat: number;
  lon: number;
  speed_kmh: number;
  fix: GnssFix;
}

export interface CargoReading {
  tag: string;
  pos: ProbePosition;
  t_c: number;
  rh: number | null;
}

export interface DoorState {
  open: boolean;
  events: number;
}

export interface Motion {
  peak_g: number;
  shock_events: number;
  vib_rms: number;
}

export interface Channel {
  i_rms: number;
  inrush_peak: number | null;
  duty_pct: number | null;
}

export interface Power {
  v_bus: number;
  compressor: Channel;
  cond_fan: Channel;
  evap_fan: Channel;
  state: CompressorState;
}

export interface Health {
  batt_v: number;
  rssi: number;
  buffer_pct: number;
  gnss_fix: GnssFix;
}

/** shared/schema.py::TelemetryPacket, as stored in telemetry.payload. */
export interface TelemetryPacket {
  device_id: string;
  shipment_id: string | null;
  mission_profile: MissionProfile | null;
  band: Band | null;
  ts: string;
  seq: number;
  buffered: boolean;
  gnss: Gnss;
  cargo: CargoReading[];
  ambient_c: number;
  door: DoorState;
  light_lux: number;
  motion: Motion;
  power: Power;
  health: Health;
  sig: string | null;
}

/** One row of the `telemetry` table (infra/schema.sql). */
export interface TelemetryRow {
  id: number;
  device_id: string;
  shipment_id: string | null;
  ts: string;
  seq: number;
  buffered: boolean;
  received_ts: string;
  payload: TelemetryPacket;
}

/** shared/schema.py::AlertRecord, as stored in alerts.payload. */
export interface AlertRecord {
  alert_id: string;
  device_id: string;
  shipment_id: string | null;
  issued_ts: string;
  tier: number;
  state: AlertState;
  severity: Severity;
  cause: FaultCause;
  evidence: Record<string, number>;
  predicted_breach_min: number | null;
  prescribed_action: PrescribedAction;
  message: string;
  ack_ts: string | null;
  driver_cause: DriverCause | null;
  action_taken: string | null;
  outcome: Outcome;
  delivered_offline: boolean;
  escalated_ts: string | null;
  resolved_ts: string | null;
}

/** One row of the `alerts` table (infra/schema.sql). */
export interface AlertRow {
  alert_id: string;
  device_id: string;
  shipment_id: string | null;
  issued_ts: string;
  state: AlertState;
  severity: Severity;
  cause: FaultCause;
  payload: AlertRecord;
  ack_ts: string | null;
  driver_cause: DriverCause | null;
  action_taken: string | null;
  outcome: Outcome;
}

export type Role = "driver" | "dispatcher" | "quality";
export type Locale = "fr" | "en" | "ar";

/** One row of the `profiles` table (infra/schema.sql). */
export interface UserProfile {
  id: string;
  role: Role;
  locale: Locale;
  display_name: string;
  created_at: string;
}

export function worstCargoC(cargo: CargoReading[]): number {
  return Math.max(...cargo.map((c) => c.t_c));
}

export function coldestCargoC(cargo: CargoReading[]): number {
  return Math.min(...cargo.map((c) => c.t_c));
}
