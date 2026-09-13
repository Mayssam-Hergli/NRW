import { useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AlertRow, Locale, TelemetryPacket } from "../lib/types";

export function DriverHistory({ packets, alerts, locale }: { packets: TelemetryPacket[]; alerts: AlertRow[]; locale: Locale }) {
  const [windowMin, setWindowMin] = useState(60);
  const t = (fr: string, en: string, ar: string) => ({ fr, en, ar })[locale];
  const latest = packets[packets.length - 1];
  if (!latest) return null;
  const data = packets.filter(p => Date.parse(p.ts) >= Date.parse(latest.ts) - windowMin * 60000).map(p => {
    const values = p.cargo.filter(c => c.pos !== "ambient_external").map(c => c.t_c);
    return { ts: Date.parse(p.ts), min: values.length ? Math.min(...values) : null, max: values.length ? Math.max(...values) : null };
  });
  const time = (ts: number) => new Date(ts).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
  return <>
    <section className="panel">
      <div className="row space-between"><h2>{t("Historique des températures", "Temperature history", "سجل درجات الحرارة")}</h2>
        <select aria-label={t("Période", "Time range", "الفترة")} style={{ width: "auto" }} value={windowMin} onChange={e => setWindowMin(Number(e.target.value))}><option value={60}>1 h</option><option value={180}>3 h</option><option value={1440}>24 h</option></select>
      </div>
      <p className="insight-note">{t("Minimum et maximum des sondes. Période relative à la dernière mesure reçue.", "Probe minimum and maximum. Time range ends at the last received reading.", "أدنى وأعلى قراءات المجسات. تنتهي الفترة عند آخر قراءة مستلمة.")}</p>
      {data.length < 2 ? <p>{t("En attente de mesures supplémentaires.", "Waiting for more readings.", "بانتظار المزيد من القراءات.")}</p> : <ResponsiveContainer width="100%" height={210}><LineChart data={data}><CartesianGrid stroke="var(--rule)" strokeDasharray="3 3" /><XAxis dataKey="ts" type="number" domain={["dataMin", "dataMax"]} tickFormatter={time} tick={{ fontSize: 10 }} /><YAxis unit="°C" tick={{ fontSize: 10 }} /><Tooltip labelFormatter={v => time(Number(v))} />{latest.band && <><ReferenceLine y={latest.band.min_c} stroke="var(--warn)" strokeDasharray="4 4" /><ReferenceLine y={latest.band.max_c} stroke="var(--warn)" strokeDasharray="4 4" /></>}<Line dataKey="min" name={t("Minimum", "Minimum", "الأدنى")} stroke="var(--primary)" dot={false} /><Line dataKey="max" name={t("Maximum", "Maximum", "الأعلى")} stroke="var(--signal-text)" dot={false} /></LineChart></ResponsiveContainer>}
    </section>
    <details className="panel driver-details"><summary>{t("Journal des alertes", "Alert history", "سجل التنبيهات")} ({alerts.length})</summary><div className="stack">
      {alerts.length === 0 && <p className="muted">{t("Aucune alerte reçue.", "No alerts received.", "لم يتم استلام تنبيهات.")}</p>}
      {alerts.map(a => <article className="driver-log" key={a.alert_id}><time>{new Date(a.issued_ts).toLocaleString(locale)}</time><p>{a.payload.message}</p><span>{a.ack_ts ? t("Acquittée", "Acknowledged", "تم الإقرار") : t("Non acquittée", "Not acknowledged", "لم يتم الإقرار")}</span>{a.action_taken && <p>{a.action_taken}</p>}</article>)}
    </div></details>
    <details className="panel driver-details"><summary>{t("Position et état de l’appareil", "Position and device health", "الموقع وحالة الجهاز")}</summary><dl className="driver-health">
      <dt>{t("Position GPS", "GPS position", "موقع GPS")}</dt><dd>{latest.gnss.fix === "NONE" ? t("Indisponible", "Unavailable", "غير متاح") : `${latest.gnss.lat.toFixed(5)}, ${latest.gnss.lon.toFixed(5)}`}</dd>
      <dt>{t("Signal mobile", "Cellular signal", "إشارة الهاتف")}</dt><dd>{latest.health.rssi} dBm</dd>
      <dt>{t("Mémoire tampon utilisée", "Buffer used", "الذاكرة المؤقتة المستخدمة")}</dt><dd>{latest.health.buffer_pct.toFixed(0)}%</dd>
      <dt>{t("Tension groupe froid", "Refrigeration voltage", "جهد التبريد")}</dt><dd>{latest.power.v_bus.toFixed(1)} V</dd>
    </dl></details>
  </>;
}
