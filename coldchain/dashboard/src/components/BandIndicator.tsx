import type { Band, Locale } from "../lib/types";

const LABEL = {
  inBand: { fr: "Dans la plage", en: "In band", ar: "ضمن النطاق" },
  aboveBand: { fr: "Trop chaud", en: "Too warm", ar: "حار جدًا" },
  belowBand: { fr: "Trop froid", en: "Too cold", ar: "بارد جدًا" },
  unknown: { fr: "Plage non définie", en: "No temperature band set", ar: "نطاق الحرارة غير محدد" },
  missing: { fr: "Aucune mesure du chargement", en: "No cargo reading", ar: "لا توجد قراءة للشحنة" },
  stale: { fr: "Dernière valeur connue", en: "Last known value", ar: "آخر قيمة معروفة" },
};

export function BandIndicator({ currentC, band, locale, stale = false }: {
  currentC: number | null;
  band: Band | null;
  locale: Locale;
  stale?: boolean;
}) {
  const valid = currentC != null && Number.isFinite(currentC);
  const validBand = band && Number.isFinite(band.min_c) && Number.isFinite(band.max_c) && band.max_c > band.min_c ? band : null;
  const state = !valid ? "missing" : stale ? "stale" : !validBand ? "unknown" : currentC! > validBand.max_c ? "aboveBand" : currentC! < validBand.min_c ? "belowBand" : "inBand";
  const color = state === "aboveBand" || state === "belowBand" ? "var(--signal-text)" : state === "inBand" ? "var(--primary)" : "var(--muted)";
  const fraction = validBand && valid ? Math.min(1, Math.max(0, (currentC! - validBand.min_c) / (validBand.max_c - validBand.min_c))) : null;

  return <div className="band-readout stack" style={{ alignItems: "center" }}>
    <div className="band-value numeric" style={{ fontSize: "clamp(3.25rem, 8vw, 4.5rem)", fontWeight: 750, lineHeight: 1.1, letterSpacing: "-.055em", color }}>
      {valid ? `${currentC!.toFixed(1)}°C` : "—"}
    </div>
    <div className="row" style={{ color, fontWeight: 600 }}>
      <span aria-hidden="true">{state === "inBand" ? "✓" : state === "aboveBand" || state === "belowBand" ? "!" : "·"}</span>
      <span>{LABEL[state][locale]}</span>
    </div>
    {validBand && <div style={{ width: "100%", marginBlockStart: ".7rem" }}>
      <div aria-hidden="true" style={{ position: "relative", height: ".5rem", borderRadius: "999px", background: "var(--nominal)" }}>
        {fraction != null && <div style={{ position: "absolute", insetBlockStart: "-.3rem", insetInlineStart: `calc(${fraction * 100}% - 5px)`, width: "10px", height: "18px", borderRadius: "5px", border: "2px solid var(--panel)", background: color }} />}
      </div>
      <div className="row space-between muted numeric" style={{ fontSize: ".85rem", marginBlockStart: ".5rem" }}>
        <span>{validBand.min_c.toFixed(1)}°C</span><span>{validBand.max_c.toFixed(1)}°C</span>
      </div>
    </div>}
  </div>;
}
