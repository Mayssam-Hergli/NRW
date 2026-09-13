import { useMemo } from "react";
import { AppHeader } from "../components/AppHeader";
import { useShipments } from "../hooks/useShipments";
import {
  readingsFromPackets,
  stabilityBudgetConsumed,
  type BudgetResult,
  type Verdict,
} from "../lib/m3";
import { getProfile } from "../lib/profiles";
import type { Locale, MissionProfile } from "../lib/types";

const UI_TEXT = {
  title: { fr: "Expéditions", en: "Shipments", ar: "الشحنات" },
  mkt: { fr: "TCM", en: "MKT", ar: "درجة الحرارة الحركية المتوسطة" },
  minutesOut: { fr: "min hors plage", en: "min out of band", ar: "دقيقة خارج النطاق" },
  coverage: { fr: "couverture", en: "coverage", ar: "التغطية" },
  certificate: { fr: "Certificat", en: "Certificate", ar: "الشهادة" },
  noShipments: {
    fr: "Aucune expédition trouvée -- la base est-elle amorcée ?",
    en: "No shipments found -- is the database seeded?",
    ar: "لم يتم العثور على شحنات -- هل تم تهيئة القاعدة؟",
  },
} satisfies Record<string, Record<Locale, string>>;

const VERDICT_LABEL: Record<Verdict, Record<Locale, string>> = {
  compliant: { fr: "Conforme", en: "Compliant", ar: "مطابق" },
  minor_deviation: { fr: "Écart mineur", en: "Minor deviation", ar: "انحراف طفيف" },
  excursion_review: { fr: "À examiner", en: "Excursion review", ar: "يتطلب المراجعة" },
};

const VERDICT_COLOR: Record<Verdict, string> = {
  compliant: "var(--primary)",
  minor_deviation: "var(--warn)",
  excursion_review: "var(--signal-text)",
};

function computeBudget(
  profile: MissionProfile,
  packets: Parameters<typeof readingsFromPackets>[0],
): BudgetResult | null {
  if (packets.length === 0) return null;
  const spec = getProfile(profile);
  const aggregate = spec.freezeAlarm
    ? (values: number[]) => Math.min(...values)
    : (values: number[]) => Math.max(...values);
  const readings = readingsFromPackets(packets, aggregate);
  if (readings.length === 0) return null;

  const timestamps = packets.map((p) => new Date(p.ts).getTime());
  const durationMin = (Math.max(...timestamps) - Math.min(...timestamps)) / 60000;
  if (durationMin <= 0) return null;

  return stabilityBudgetConsumed(
    readings,
    profile,
    {
      minC: spec.minC,
      maxC: spec.maxC,
      freezeAlarm: spec.freezeAlarm,
      cumulativeExcursionLimitMin: spec.cumulativeExcursionLimitMin,
    },
    durationMin,
  );
}

export function QualityView({
  locale,
  onOpenCertificate,
}: {
  locale: Locale;
  onOpenCertificate: (shipmentId: string) => void;
}) {
  const { shipments, connection } = useShipments();

  const rows = useMemo(
    () =>
      shipments
        .filter((s) => s.profile !== null)
        .map((s) => ({
          shipment: s,
          budget: computeBudget(s.profile as MissionProfile, s.packets),
        }))
        .filter((r): r is { shipment: (typeof shipments)[number]; budget: BudgetResult } =>
          r.budget !== null,
        ),
    [shipments],
  );

  return (
    <div>
      <AppHeader connection={connection} locale={locale} />
      <div className="page wide stack">
        <div style={{ fontWeight: 700 }}>{UI_TEXT.title[locale]}</div>

        {rows.length === 0 && <div className="panel muted">{UI_TEXT.noShipments[locale]}</div>}

        {rows.map(({ shipment, budget }) => (
          <div key={shipment.shipmentId} className="panel stack">
            <div className="row space-between">
              <div>
                <div style={{ fontWeight: 700 }}>{shipment.shipmentId}</div>
                <div className="muted" style={{ fontSize: "0.85rem" }}>
                  {shipment.deviceId}
                </div>
              </div>
              <span style={{ color: VERDICT_COLOR[budget.verdict], fontWeight: 700 }}>
                ● {VERDICT_LABEL[budget.verdict][locale]}
              </span>
            </div>

            <div className="row space-between numeric" style={{ fontSize: "0.9rem" }}>
              <span>
                {UI_TEXT.mkt[locale]}: {budget.mktC.toFixed(1)}°C
              </span>
              <span>
                {(budget.minutesOutOfBandAbove + budget.minutesOutOfBandBelow).toFixed(0)}{" "}
                {UI_TEXT.minutesOut[locale]}
              </span>
              <span>
                {budget.coveragePct.toFixed(1)}% {UI_TEXT.coverage[locale]}
              </span>
            </div>

            <button
              type="button"
              className="secondary"
              style={{ alignSelf: "flex-start", fontSize: "0.8rem", padding: "0.4rem 0.75rem" }}
              onClick={() => onOpenCertificate(shipment.shipmentId)}
            >
              {UI_TEXT.certificate[locale]} →
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
