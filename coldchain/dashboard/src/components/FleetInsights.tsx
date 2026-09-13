import { useEffect, useState } from "react";
import type { FleetEntry } from "../hooks/useFleet";
import type { Locale } from "../lib/types";

const labels = {
  title: { fr: "Centre de supervision", en: "Operations overview", ar: "نظرة عامة على العمليات" },
  subtitle: { fr: "Priorisez les interventions à partir des dernières mesures reçues.", en: "Prioritize interventions using the latest received readings.", ar: "حدد أولويات التدخل وفق أحدث القراءات المستلمة." },
  vehicles: { fr: "Véhicules observés", en: "Observed vehicles", ar: "المركبات المرصودة" },
  alerts: { fr: "Alertes à acquitter", en: "Alerts awaiting acknowledgment", ar: "تنبيهات تنتظر الإقرار" },
  excursion: { fr: "Véhicules hors plage", en: "Vehicles outside band", ar: "مركبات خارج النطاق" },
  stale: { fr: "Sans mesure récente", en: "No recent reading", ar: "دون قراءة حديثة" },
  note: { fr: "Une mesure de plus de 5 minutes est considérée comme ancienne. Une connexion active ne garantit pas des données récentes.", en: "Readings older than 5 minutes are stale. An active connection does not guarantee fresh data.", ar: "تعد القراءات الأقدم من 5 دقائق قديمة. الاتصال النشط لا يضمن بيانات حديثة." },
};

export function FleetInsights({ entries, locale }: { entries: FleetEntry[]; locale: Locale }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(timer); }, []);
  const stale = entries.filter(e => now - Date.parse(e.latest.ts) > 300000).length;
  const excursions = entries.filter(({ latest: p }) => p.band && p.cargo.some(c => c.pos !== "ambient_external" && (c.t_c < p.band!.min_c || c.t_c > p.band!.max_c))).length;
  const alerts = entries.reduce((sum, e) => sum + e.activeAlerts.filter(a => !a.ack_ts).length, 0);
  return <section className="overview" aria-label={labels.title[locale]}>
    <div className="view-heading"><span className="eyebrow">VALLUM / OPERATIONS</span><h1>{labels.title[locale]}</h1><p>{labels.subtitle[locale]}</p></div>
    <div className="metrics-grid">
      {[[labels.vehicles[locale], entries.length], [labels.alerts[locale], alerts], [labels.excursion[locale], excursions], [labels.stale[locale], stale]].map(([label, count], index) => <div className="metric-card" key={label}>
        <span>{label}</span><strong className={index > 0 && Number(count) > 0 ? "attention numeric" : "numeric"}>{count}</strong>
      </div>)}
    </div>
    <p className="insight-note">{labels.note[locale]}</p>
  </section>;
}
