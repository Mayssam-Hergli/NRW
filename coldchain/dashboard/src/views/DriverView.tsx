import { useMemo } from "react";
import { AlertBanner } from "../components/AlertBanner";
import { AppHeader } from "../components/AppHeader";
import { BandIndicator } from "../components/BandIndicator";
import { useAlerts } from "../hooks/useAlerts";
import { useFleet } from "../hooks/useFleet";
import { useTelemetryHistory } from "../hooks/useTelemetryHistory";
import { useAuth } from "../lib/auth";
import { worstCargoC } from "../lib/types";
import type { Locale } from "../lib/types";

const ACTIVE_STATES = new Set(["watch", "warning", "critical", "escalated"]);

const UI_TEXT = {
  greeting: { fr: "Bonjour", en: "Hello", ar: "مرحبًا" },
  unitState: {
    RUN: { fr: "Groupe en marche", en: "Unit running", ar: "الوحدة تعمل" },
    OFF: { fr: "Groupe à l'arrêt", en: "Unit off", ar: "الوحدة متوقفة" },
    SHORT_CYCLE: { fr: "Cycles courts", en: "Short cycling", ar: "دورات قصيرة" },
    FAULT: { fr: "Panne du groupe", en: "Unit fault", ar: "عطل بالوحدة" },
  },
  timeRemaining: { fr: "Dépassement dans", en: "Breach in", ar: "التجاوز خلال" },
  min: { fr: "min", en: "min", ar: "د" },
  pullOver: {
    fr: "Arrêtez-vous en sécurité, puis vérifiez.",
    en: "Pull over safely, then check.",
    ar: "توقف بأمان، ثم تحقق.",
  },
  acknowledge: { fr: "J'ai vu", en: "Acknowledge", ar: "تم الاطلاع" },
  noDevice: {
    fr: "Aucun véhicule trouvé -- la base est-elle amorcée ?",
    en: "No vehicle found -- is the database seeded?",
    ar: "لم يتم العثور على مركبة -- هل تم تهيئة القاعدة؟",
  },
  vehicle: { fr: "Véhicule", en: "Vehicle", ar: "المركبة" },
  shipment: { fr: "Expédition", en: "Shipment", ar: "الشحنة" },
  door: { fr: "Porte", en: "Door", ar: "الباب" },
  doorOpen: { fr: "ouverte", en: "open", ar: "مفتوح" },
  doorClosed: { fr: "fermée", en: "closed", ar: "مغلق" },
  ambient: { fr: "Extérieur", en: "Outside", ar: "الخارج" },
  battery: { fr: "Batterie appareil", en: "Device battery", ar: "بطارية الجهاز" },
  allClear: { fr: "Tout va bien.", en: "Everything's fine.", ar: "كل شيء على ما يرام." },
} satisfies Record<string, unknown>;

export function DriverView({ locale }: { locale: Locale }) {
  const { profile } = useAuth();

  // This demo runs one truck; a real fleet would map driver -> assigned
  // device via a column this schema doesn't have yet. Defaulting to
  // whichever device has the most recent telemetry keeps this honest
  // about that simplification rather than hardcoding a device id.
  const { entries, connection: fleetConnection } = useFleet();
  const deviceId = entries[0]?.deviceId ?? null;

  const { packets, connection } = useTelemetryHistory(deviceId);
  const { alerts, acknowledge } = useAlerts(deviceId);
  const latest = packets[packets.length - 1];

  const activeAlert = useMemo(
    () => alerts.find((a) => ACTIVE_STATES.has(a.state) && !a.ack_ts),
    [alerts],
  );

  if (!deviceId || !latest) {
    return (
      <div>
        <AppHeader connection={fleetConnection} locale={locale} />
        <div className="page stack">
          <div className="panel muted">{UI_TEXT.noDevice[locale]}</div>
        </div>
      </div>
    );
  }

  const moving = latest.gnss.speed_kmh > 0;
  const worst = worstCargoC(latest.cargo);
  const critical = activeAlert?.severity === "critical";

  // Moving: one line, large text, single tap, nothing else. If severity
  // is critical the instruction becomes the fixed pull-over line
  // regardless of the alert's own cause-specific copy.
  if (moving) {
    return (
      <div className="page stack" style={{ paddingBlockStart: "2rem" }}>
        {activeAlert ? (
          <div
            style={{ background: "var(--signal)", color: "#fff", borderRadius: "1.25rem", padding: "1.75rem" }}
          >
            <div className="stack">
              <div style={{ fontSize: "1.5rem", fontWeight: 700, lineHeight: 1.3 }}>
                {critical ? UI_TEXT.pullOver[locale] : activeAlert.payload.message}
              </div>
              <button
                style={{ background: "#fff", color: "var(--signal-text)", fontWeight: 700, fontSize: "1.1rem" }}
                onClick={() => void acknowledge(activeAlert.alert_id, {})}
              >
                {UI_TEXT.acknowledge[locale]}
              </button>
            </div>
          </div>
        ) : (
          <div
            className="stack"
            style={{
              alignItems: "center",
              background: "var(--panel)",
              border: "1px solid var(--rule)",
              borderRadius: "1.25rem",
              padding: "2rem",
            }}
          >
            <div className="numeric" style={{ fontSize: "3.5rem", fontWeight: 700, color: "var(--primary)" }}>
              {worst.toFixed(1)}°C
            </div>
            <div className="muted">{UI_TEXT.allClear[locale]}</div>
          </div>
        )}
      </div>
    );
  }

  // Stationary: full detail, cause selection, history.
  return (
    <div>
      <AppHeader connection={connection} locale={locale} />
      <div className="page stack">
        {profile && (
          <div className="muted" style={{ fontSize: "0.9rem" }}>
            {UI_TEXT.greeting[locale]}, {profile.display_name}
          </div>
        )}

        <div className="panel">
          <BandIndicator currentC={worst} band={latest.band} locale={locale} />
        </div>

        <div className="panel stack" style={{ fontSize: "0.9rem" }}>
          <div className="row space-between">
            <span className="muted">{UI_TEXT.vehicle[locale]}</span>
            <span style={{ fontWeight: 600 }}>{latest.device_id}</span>
          </div>
          {latest.shipment_id && (
            <div className="row space-between">
              <span className="muted">{UI_TEXT.shipment[locale]}</span>
              <span>{latest.shipment_id}</span>
            </div>
          )}
          <div className="row space-between">
            <span className="muted">{UI_TEXT.door[locale]}</span>
            <span>{latest.door.open ? UI_TEXT.doorOpen[locale] : UI_TEXT.doorClosed[locale]}</span>
          </div>
          <div className="row space-between numeric">
            <span className="muted">{UI_TEXT.ambient[locale]}</span>
            <span>{latest.ambient_c.toFixed(1)}°C</span>
          </div>
          <div className="row space-between numeric">
            <span className="muted">{UI_TEXT.battery[locale]}</span>
            <span>{latest.health.batt_v.toFixed(1)} V</span>
          </div>
        </div>

        <div className="panel row space-between">
          <span>{UI_TEXT.unitState[latest.power.state][locale]}</span>
          {activeAlert?.payload.predicted_breach_min != null && (
            <span className="numeric">
              {UI_TEXT.timeRemaining[locale]} {activeAlert.payload.predicted_breach_min.toFixed(0)}{" "}
              {UI_TEXT.min[locale]}
            </span>
          )}
        </div>

        {activeAlert && <AlertBanner alert={activeAlert} locale={locale} />}
      </div>
    </div>
  );
}
