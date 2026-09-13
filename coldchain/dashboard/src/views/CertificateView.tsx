import { useEffect, useMemo, useState } from "react";
import { Logo } from "../components/Logo";
import { useShipments } from "../hooks/useShipments";
import { readingsFromPackets, stabilityBudgetConsumed, type Verdict } from "../lib/m3";
import { getProfile } from "../lib/profiles";
import type { Locale, MissionProfile } from "../lib/types";

const TEXT = {
  title: { fr: "Certificat de conformité", en: "Compliance certificate", ar: "شهادة المطابقة" },
  back: { fr: "← Retour", en: "← Back", ar: "→ رجوع" },
  shipment: { fr: "Expédition", en: "Shipment", ar: "الشحنة" },
  vehicle: { fr: "Véhicule", en: "Vehicle", ar: "المركبة" },
  verdict: { fr: "Verdict", en: "Verdict", ar: "الحكم" },
  mkt: { fr: "Température moyenne cinétique", en: "Mean kinetic temperature", ar: "متوسط درجة الحرارة الحركية" },
  minutesOut: { fr: "Minutes hors plage", en: "Minutes out of band", ar: "الدقائق خارج النطاق" },
  coverage: { fr: "Couverture des données", en: "Data coverage", ar: "تغطية البيانات" },
  shelfLife: { fr: "Durée de conservation consommée", en: "Shelf life consumed", ar: "مدة الصلاحية المستهلكة" },
  hash: { fr: "Hachage de vérification", en: "Verification hash", ar: "رمز التحقق" },
  hashNote: {
    fr: "Empreinte SHA-256 calculée à partir de ce relevé, côté client -- une preuve d'intégrité du calcul affiché, pas encore une chaîne de hachage inviolable établie à la collecte.",
    en: "Client-computed SHA-256 fingerprint of this record -- proof the displayed calculation hasn't been altered in transit, not yet a tamper-evident chain established at collection time.",
    ar: "بصمة SHA-256 محسوبة من طرف العميل لهذا السجل -- إثبات لعدم تغيير الحساب المعروض أثناء النقل، وليست بعد سلسلة تحقق مقاومة للعبث تُنشأ عند الجمع.",
  },
  notFound: { fr: "Expédition introuvable.", en: "Shipment not found.", ar: "لم يتم العثور على الشحنة." },
  loading: { fr: "Calcul en cours...", en: "Computing...", ar: "جارٍ الحساب..." },
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

async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function CertificateView({ shipmentId, locale, onBack }: { shipmentId: string; locale: Locale; onBack: () => void }) {
  const { shipments } = useShipments();
  const shipment = shipments.find((s) => s.shipmentId === shipmentId);
  const [hash, setHash] = useState<string | null>(null);

  const budget = useMemo(() => {
    if (!shipment?.profile) return null;
    const spec = getProfile(shipment.profile as MissionProfile);
    const aggregate = spec.freezeAlarm
      ? (values: number[]) => Math.min(...values)
      : (values: number[]) => Math.max(...values);
    const readings = readingsFromPackets(shipment.packets, aggregate);
    if (readings.length === 0) return null;
    const timestamps = shipment.packets.map((p) => new Date(p.ts).getTime());
    const durationMin = (Math.max(...timestamps) - Math.min(...timestamps)) / 60000;
    if (durationMin <= 0) return null;
    return stabilityBudgetConsumed(
      readings,
      shipment.profile as MissionProfile,
      {
        minC: spec.minC,
        maxC: spec.maxC,
        freezeAlarm: spec.freezeAlarm,
        cumulativeExcursionLimitMin: spec.cumulativeExcursionLimitMin,
      },
      durationMin,
    );
  }, [shipment]);

  useEffect(() => {
    if (!shipment || !budget) return;
    const record = {
      shipmentId: shipment.shipmentId,
      deviceId: shipment.deviceId,
      profile: shipment.profile,
      packetCount: shipment.packets.length,
      mktC: budget.mktC,
      verdict: budget.verdict,
      coveragePct: budget.coveragePct,
    };
    sha256Hex(JSON.stringify(record)).then(setHash);
  }, [shipment, budget]);

  return (
    <div className="page stack">
      <div className="row space-between">
        <Logo height={26} />
        <button className="secondary" onClick={onBack} style={{ fontSize: "0.8rem" }}>
          {TEXT.back[locale]}
        </button>
      </div>

      <h1 style={{ fontSize: "1.25rem" }}>{TEXT.title[locale]}</h1>

      {!shipment && <div className="panel muted">{TEXT.notFound[locale]}</div>}
      {shipment && !budget && <div className="panel muted">{TEXT.loading[locale]}</div>}

      {shipment && budget && (
        <div className="panel stack">
          <div className="row space-between">
            <span className="muted">{TEXT.shipment[locale]}</span>
            <span style={{ fontWeight: 700 }}>{shipment.shipmentId}</span>
          </div>
          <div className="row space-between">
            <span className="muted">{TEXT.vehicle[locale]}</span>
            <span>{shipment.deviceId}</span>
          </div>
          <div className="row space-between">
            <span className="muted">{TEXT.verdict[locale]}</span>
            <span style={{ color: VERDICT_COLOR[budget.verdict], fontWeight: 700 }}>
              ● {VERDICT_LABEL[budget.verdict][locale]}
            </span>
          </div>
          <hr style={{ border: "none", borderBlockStart: "1px solid var(--rule)", width: "100%" }} />
          <div className="row space-between numeric">
            <span className="muted">{TEXT.mkt[locale]}</span>
            <span>{budget.mktC.toFixed(2)}°C</span>
          </div>
          <div className="row space-between numeric">
            <span className="muted">{TEXT.minutesOut[locale]}</span>
            <span>{(budget.minutesOutOfBandAbove + budget.minutesOutOfBandBelow).toFixed(0)}</span>
          </div>
          <div className="row space-between numeric">
            <span className="muted">{TEXT.coverage[locale]}</span>
            <span>{budget.coveragePct.toFixed(1)}%</span>
          </div>
          <div className="row space-between numeric">
            <span className="muted">{TEXT.shelfLife[locale]}</span>
            <span>{budget.pctConsumed.toFixed(2)}%</span>
          </div>
          <hr style={{ border: "none", borderBlockStart: "1px solid var(--rule)", width: "100%" }} />
          <div>
            <div className="muted" style={{ fontSize: "0.8rem" }}>
              {TEXT.hash[locale]}
            </div>
            <div className="numeric" style={{ fontSize: "0.75rem", wordBreak: "break-all" }}>
              {hash ?? "…"}
            </div>
            <div className="muted" style={{ fontSize: "0.7rem", marginBlockStart: "0.35rem" }}>
              {TEXT.hashNote[locale]}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
