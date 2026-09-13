import type { ConnectionState } from "../hooks/useTelemetryHistory";
import type { Locale } from "../lib/types";
import "../styles/workspace-shell.css";

const LABEL: Record<ConnectionState, Record<Locale, string>> = {
  connected: { fr: "Connecté", en: "Connected", ar: "متصل" },
  connecting: { fr: "Connexion…", en: "Connecting…", ar: "جارٍ الاتصال…" },
  disconnected: { fr: "Hors ligne", en: "Offline", ar: "غير متصل" },
};

const DETAIL: Record<ConnectionState, Record<Locale, string>> = {
  connected: {
    fr: "Connexion au service active. Vérifiez l’heure des mesures pour connaître leur fraîcheur.",
    en: "Service connection is active. Check reading times to see how recent the data is.",
    ar: "الاتصال بالخدمة نشط. تحقق من وقت القياسات لمعرفة حداثة البيانات.",
  },
  connecting: {
    fr: "Connexion au service en cours. Les mesures affichées peuvent être anciennes.",
    en: "Connecting to the service. Displayed readings may be old.",
    ar: "جارٍ الاتصال بالخدمة. قد تكون القياسات المعروضة قديمة.",
  },
  disconnected: {
    fr: "Mises à jour interrompues. Vérifiez la connexion et l’heure des dernières mesures.",
    en: "Updates interrupted. Check your connection and the time of the latest readings.",
    ar: "توقفت التحديثات. تحقق من اتصالك ووقت آخر القياسات.",
  },
};

/** Connection status is distinct from freshness of the sensor readings. */
export function ConnectionBadge({ state, locale }: { state: ConnectionState; locale: Locale }) {
  return (
    <span className={`connection-badge connection-badge--${state}`} role="status" title={DETAIL[state][locale]}>
      <span className="connection-dot" aria-hidden="true" />
      <span>{LABEL[state][locale]}</span>
      <span className="workspace-sr-only">. {DETAIL[state][locale]}</span>
    </span>
  );
}
