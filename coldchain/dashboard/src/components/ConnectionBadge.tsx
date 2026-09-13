import type { ConnectionState } from "../hooks/useTelemetryHistory";
import type { Locale } from "../lib/types";

const LABEL: Record<ConnectionState, Record<Locale, string>> = {
  connected: { fr: "En direct", en: "Live", ar: "مباشر" },
  connecting: { fr: "Connexion...", en: "Connecting...", ar: "جارٍ الاتصال..." },
  disconnected: { fr: "Hors ligne", en: "Offline", ar: "غير متصل" },
};

const ICON: Record<ConnectionState, string> = {
  connected: "●",
  connecting: "◐",
  disconnected: "○",
};

const COLOR: Record<ConnectionState, string> = {
  connected: "var(--nominal)",
  connecting: "var(--muted)",
  disconnected: "var(--signal-text)",
};

/** Colour + icon + word, never colour alone (design rule). */
export function ConnectionBadge({ state, locale }: { state: ConnectionState; locale: Locale }) {
  return (
    <span
      className="row"
      style={{
        color: COLOR[state],
        fontSize: "0.8rem",
        fontWeight: 600,
        gap: "0.35rem",
      }}
    >
      <span aria-hidden="true">{ICON[state]}</span>
      <span>{LABEL[state][locale]}</span>
    </span>
  );
}
