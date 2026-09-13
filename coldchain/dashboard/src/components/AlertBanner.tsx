import { useState } from "react";
import { useAlerts } from "../hooks/useAlerts";
import { renderSafe } from "../i18n/messages";
import type { AlertRow, DriverCause, Locale } from "../lib/types";

// shared/messages.py has no catalogue for DriverCause (only FaultCause) --
// these are the driver's own short-list options after acknowledging, not
// system-generated copy, so they're hand-localized here rather than
// pretending there's a Python source of truth for them.
const DRIVER_CAUSE_LABEL: Record<DriverCause, Record<Locale, string>> = {
  offload_stop: { fr: "Arrêt de déchargement", en: "Offload stop", ar: "توقف للتفريغ" },
  door_left_open: { fr: "Porte restée ouverte", en: "Door left open", ar: "الباب بقي مفتوحًا" },
  unit_failure: { fr: "Panne du groupe froid", en: "Unit failure", ar: "عطل في وحدة التبريد" },
  power_issue: { fr: "Problème électrique", en: "Power issue", ar: "مشكلة كهربائية" },
  loading_delay: { fr: "Retard de chargement", en: "Loading delay", ar: "تأخر في التحميل" },
  other: { fr: "Autre", en: "Other", ar: "أخرى" },
};

const UI_TEXT = {
  acknowledge: { fr: "J'ai vu", en: "Acknowledge", ar: "تم الاطلاع" },
  whatHappened: { fr: "Cause probable ?", en: "What happened?", ar: "ما السبب المحتمل؟" },
  actionTaken: { fr: "Action effectuée", en: "Action taken", ar: "الإجراء المتخذ" },
  actionPlaceholder: {
    fr: "Décrire brièvement...",
    en: "Briefly describe...",
    ar: "صف بإيجاز...",
  },
  confirm: { fr: "Confirmer", en: "Confirm", ar: "تأكيد" },
  confirmed: { fr: "Confirmé, merci.", en: "Confirmed, thanks.", ar: "تم التأكيد، شكرًا." },
} satisfies Record<string, Record<Locale, string>>;

export function AlertBanner({ alert, locale }: { alert: AlertRow; locale: Locale }) {
  const { acknowledge, writeError } = useAlerts(alert.device_id);
  const [step, setStep] = useState<"alert" | "cause" | "done">(alert.ack_ts ? "done" : "alert");
  const [selectedCause, setSelectedCause] = useState<DriverCause | null>(null);
  const [actionTaken, setActionTaken] = useState("");

  // render() throws on a missing placeholder (by design -- see
  // i18n/messages.ts) rather than emitting a half-filled sentence. A
  // non-watch severity without predicted_breach_min would hit that:
  // renderSafe falls back to the alert's own stored message rather than
  // crashing the driver's screen over an upstream data gap.
  const driverText = renderSafe(
    {
      cause: alert.cause,
      severity: alert.severity,
      audience: "driver",
      locale,
      evidence: alert.payload.evidence,
      ctx:
        alert.payload.predicted_breach_min != null
          ? { eta_min: alert.payload.predicted_breach_min }
          : {},
    },
    alert.payload.message,
  );

  async function handleAcknowledge() {
    try {
      await acknowledge(alert.alert_id, {});
      setStep("cause");
    } catch {
      // writeError is already surfaced below
    }
  }

  async function handleConfirm() {
    try {
      await acknowledge(alert.alert_id, {
        driverCause: selectedCause ?? undefined,
        actionTaken: actionTaken || undefined,
        outcome: "pending",
      });
      setStep("done");
    } catch {
      // writeError is already surfaced below
    }
  }

  if (step === "done") {
    return (
      <div className="panel" style={{ borderColor: "var(--nominal)" }}>
        {UI_TEXT.confirmed[locale]}
      </div>
    );
  }

  return (
    <div
      style={{
        background: "var(--signal)",
        color: "#ffffff",
        borderRadius: "1rem",
        padding: "1.25rem",
      }}
    >
      <div className="stack">
        <div style={{ fontSize: "1.25rem", fontWeight: 700 }}>{driverText}</div>

        {step === "alert" && (
          <button
            onClick={handleAcknowledge}
            style={{ background: "#ffffff", color: "var(--signal-text)", fontWeight: 700 }}
          >
            {UI_TEXT.acknowledge[locale]}
          </button>
        )}

        {step === "cause" && (
          <div className="stack">
            <div>{UI_TEXT.whatHappened[locale]}</div>
            <div className="row">
              {(Object.keys(DRIVER_CAUSE_LABEL) as DriverCause[]).map((cause) => (
                <button
                  key={cause}
                  onClick={() => setSelectedCause(cause)}
                  style={{
                    background: selectedCause === cause ? "#ffffff" : "transparent",
                    color: selectedCause === cause ? "var(--signal-text)" : "#ffffff",
                    border: "1px solid #ffffff",
                  }}
                >
                  {DRIVER_CAUSE_LABEL[cause][locale]}
                </button>
              ))}
            </div>
            <label style={{ color: "#ffffff" }}>{UI_TEXT.actionTaken[locale]}</label>
            <input
              value={actionTaken}
              onChange={(e) => setActionTaken(e.target.value)}
              placeholder={UI_TEXT.actionPlaceholder[locale]}
            />
            <button
              onClick={handleConfirm}
              disabled={!selectedCause}
              style={{ background: "#ffffff", color: "var(--signal-text)", fontWeight: 700 }}
            >
              {UI_TEXT.confirm[locale]}
            </button>
          </div>
        )}

        {writeError && <div style={{ color: "#ffffff", fontSize: "0.8rem" }}>{writeError}</div>}
      </div>
    </div>
  );
}
