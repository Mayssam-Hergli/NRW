import { useMemo } from "react";
import { AlertBanner } from "../components/AlertBanner";
import { BandIndicator } from "../components/BandIndicator";
import { ConnectionBadge } from "../components/ConnectionBadge";
import { RoleSwitcher } from "../components/RoleSwitcher";
import { useAlerts } from "../hooks/useAlerts";
import { useFleet } from "../hooks/useFleet";
import { useTelemetryHistory } from "../hooks/useTelemetryHistory";
import { useAuth } from "../lib/auth";
import { worstCargoC } from "../lib/types";
import type { Locale } from "../lib/types";

const ACTIVE_STATES = new Set(["watch", "warning", "critical", "escalated"]);

const UI_TEXT = {
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
} satisfies Record<string, unknown>;

export function DriverView() {
  const { profile } = useAuth();
  const locale: Locale = profile?.locale ?? "fr";

  // This demo runs one truck; a real fleet would map driver -> assigned
  // device via a column this schema doesn't have yet. Defaulting to
  // whichever device has the most recent telemetry keeps this honest
  // about that simplification rather than hardcoding a device id.
  const { entries } = useFleet();
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
      <div className="page stack">
        <RoleSwitcher locale={locale} />
        <div className="panel muted">{UI_TEXT.noDevice[locale]}</div>
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
            style={{ background: "var(--signal)", color: "#fff", borderRadius: "1rem", padding: "1.5rem" }}
          >
            <div className="stack">
              <div style={{ fontSize: "1.4rem", fontWeight: 700 }}>
                {critical ? UI_TEXT.pullOver[locale] : activeAlert.payload.message}
              </div>
              <button
                style={{ background: "#fff", color: "var(--signal-text)", fontWeight: 700 }}
                onClick={() => void acknowledge(activeAlert.alert_id, {})}
              >
                {UI_TEXT.acknowledge[locale]}
              </button>
            </div>
          </div>
        ) : (
          <div className="numeric" style={{ fontSize: "3rem", fontWeight: 700, color: "var(--primary)" }}>
            {worst.toFixed(1)}°C
          </div>
        )}
      </div>
    );
  }

  // Stationary: full detail, cause selection, history.
  return (
    <div className="page stack">
      <div className="row space-between">
        <ConnectionBadge state={connection} locale={locale} />
        <RoleSwitcher locale={locale} />
      </div>

      <div className="panel">
        <BandIndicator currentC={worst} band={latest.band} locale={locale} />
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
  );
}
