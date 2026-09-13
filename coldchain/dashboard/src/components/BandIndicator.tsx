import type { Band, Locale } from "../lib/types";

const LABEL = {
  inBand: { fr: "Dans la plage", en: "In band", ar: "ضمن النطاق" },
  aboveBand: { fr: "Trop chaud", en: "Too warm", ar: "حار جدًا" },
  belowBand: { fr: "Trop froid", en: "Too cold", ar: "بارد جدًا" },
};

export function BandIndicator({
  currentC,
  band,
  locale,
}: {
  currentC: number;
  band: Band | null;
  locale: Locale;
}) {
  const state = !band
    ? "inBand"
    : currentC > band.max_c
      ? "aboveBand"
      : currentC < band.min_c
        ? "belowBand"
        : "inBand";

  const color = state === "inBand" ? "var(--primary)" : "var(--signal-text)";
  const icon = state === "inBand" ? "✓" : "⚠";

  const fraction =
    band && band.max_c > band.min_c
      ? Math.min(1, Math.max(0, (currentC - band.min_c) / (band.max_c - band.min_c)))
      : 0.5;

  return (
    <div className="stack" style={{ alignItems: "center" }}>
      <div
        className="numeric"
        style={{ fontSize: "4rem", fontWeight: 700, lineHeight: 1, color }}
      >
        {currentC.toFixed(1)}°C
      </div>
      <div className="row" style={{ color, fontWeight: 600 }}>
        <span aria-hidden="true">{icon}</span>
        <span>{LABEL[state][locale]}</span>
      </div>
      {band && (
        <div style={{ width: "100%" }}>
          <div
            style={{
              position: "relative",
              height: "0.6rem",
              borderRadius: "999px",
              background: "var(--nominal)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                position: "absolute",
                insetBlock: 0,
                insetInlineStart: `${fraction * 100}%`,
                width: "3px",
                background: color,
              }}
            />
          </div>
          <div className="row space-between muted numeric" style={{ fontSize: "0.75rem" }}>
            <span>{band.min_c.toFixed(1)}°C</span>
            <span>{band.max_c.toFixed(1)}°C</span>
          </div>
        </div>
      )}
    </div>
  );
}
