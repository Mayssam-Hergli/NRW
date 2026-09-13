import { useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ConnectionBadge } from "../components/ConnectionBadge";
import { RoleSwitcher } from "../components/RoleSwitcher";
import { useAlerts } from "../hooks/useAlerts";
import { useFleet } from "../hooks/useFleet";
import { useTelemetryHistory } from "../hooks/useTelemetryHistory";
import { expectedDutyPct } from "../lib/expectedDuty";
import { renderSafe } from "../i18n/messages";
import { useAuth } from "../lib/auth";
import { worstCargoC } from "../lib/types";
import type { Locale } from "../lib/types";

const UI_TEXT = {
  fleet: { fr: "Flotte", en: "Fleet", ar: "الأسطول" },
  cargoTemp: { fr: "Température du chargement", en: "Cargo temperature", ar: "درجة حرارة الشحنة" },
  dutyChart: {
    fr: "Cycle de service vs référence attendue",
    en: "Duty cycle vs expected baseline",
    ar: "دورة التشغيل مقابل الأساس المتوقع",
  },
  actual: { fr: "Réel", en: "Actual", ar: "الفعلي" },
  expected: { fr: "Attendu", en: "Expected", ar: "المتوقع" },
  alerts: { fr: "Alertes", en: "Alerts", ar: "التنبيهات" },
  acked: { fr: "traité", en: "acked", ar: "تمت المعالجة" },
  pending: { fr: "en attente", en: "pending", ar: "قيد الانتظار" },
  noSelection: {
    fr: "Sélectionnez un véhicule pour le détail",
    en: "Select a vehicle for detail",
    ar: "اختر مركبة لعرض التفاصيل",
  },
} satisfies Record<string, Record<Locale, string>>;

const SEVERITY_COLOR: Record<string, string> = {
  critical: "var(--signal-text)",
  warning: "var(--warn)",
  watch: "var(--muted)",
};

function timeLabel(ts: string): string {
  return new Date(ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function DispatcherView() {
  const { profile } = useAuth();
  const locale: Locale = profile?.locale ?? "fr";

  const { entries, connection } = useFleet();
  const [selected, setSelected] = useState<string | null>(null);
  const deviceId = selected ?? entries[0]?.deviceId ?? null;

  const { packets } = useTelemetryHistory(deviceId);
  const { alerts } = useAlerts(deviceId);

  const chartData = useMemo(
    () =>
      packets.map((p) => {
        const setpoint = p.band ? (p.band.min_c + p.band.max_c) / 2 : p.ambient_c;
        return {
          ts: timeLabel(p.ts),
          cargoC: worstCargoC(p.cargo),
          minC: p.band?.min_c,
          maxC: p.band?.max_c,
          dutyPct: p.power.compressor.duty_pct ?? 0,
          expectedDutyPct: expectedDutyPct(p.ambient_c, p.gnss.speed_kmh, setpoint),
        };
      }),
    [packets],
  );

  return (
    <div className="page wide stack">
      <div className="row space-between">
        <ConnectionBadge state={connection} locale={locale} />
        <RoleSwitcher locale={locale} />
      </div>

      <div className="panel">
        <div style={{ fontWeight: 700, marginBlockEnd: "0.5rem" }}>{UI_TEXT.fleet[locale]}</div>
        <div className="stack">
          {entries.map((entry) => {
            const worst = entry.activeAlerts.reduce<string | null>((acc, a) => {
              if (a.severity === "critical") return "critical";
              if (a.severity === "warning" && acc !== "critical") return "warning";
              if (a.severity === "watch" && !acc) return "watch";
              return acc;
            }, null);
            return (
              <button
                key={entry.deviceId}
                className={entry.deviceId === deviceId ? "" : "secondary"}
                onClick={() => setSelected(entry.deviceId)}
                style={{ textAlign: "start" }}
              >
                <span className="row space-between">
                  <span>{entry.deviceId}</span>
                  <span className="numeric">{worstCargoC(entry.latest.cargo).toFixed(1)}°C</span>
                  {worst && (
                    <span style={{ color: SEVERITY_COLOR[worst], fontWeight: 700 }}>● {worst}</span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {!deviceId ? (
        <div className="panel muted">{UI_TEXT.noSelection[locale]}</div>
      ) : (
        <>
          <div className="panel">
            <div style={{ fontWeight: 700, marginBlockEnd: "0.5rem" }}>{UI_TEXT.cargoTemp[locale]}</div>
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={chartData}>
                <CartesianGrid stroke="var(--rule)" strokeDasharray="3 3" />
                <XAxis dataKey="ts" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} unit="°C" />
                <Tooltip />
                {chartData[0]?.minC != null && (
                  <ReferenceLine y={chartData[0].minC} stroke="var(--warn)" strokeDasharray="4 4" />
                )}
                {chartData[0]?.maxC != null && (
                  <ReferenceLine y={chartData[0].maxC} stroke="var(--warn)" strokeDasharray="4 4" />
                )}
                <Line type="monotone" dataKey="cargoC" stroke="var(--primary)" dot={false} strokeWidth={2} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* The most persuasive chart: electrical strain rising while
              temperature is still fine. Expected duty is shaded as an
              area; actual duty drawn on top so any divergence above the
              shaded baseline reads immediately as "working harder than it
              should for these conditions." */}
          <div className="panel">
            <div style={{ fontWeight: 700, marginBlockEnd: "0.5rem" }}>{UI_TEXT.dutyChart[locale]}</div>
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={chartData}>
                <CartesianGrid stroke="var(--rule)" strokeDasharray="3 3" />
                <XAxis dataKey="ts" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} unit="%" domain={[0, 100]} />
                <Tooltip />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="expectedDutyPct"
                  name={UI_TEXT.expected[locale]}
                  stroke="var(--nominal)"
                  fill="var(--nominal)"
                  fillOpacity={0.4}
                />
                <Line
                  type="monotone"
                  dataKey="dutyPct"
                  name={UI_TEXT.actual[locale]}
                  stroke="var(--signal)"
                  dot={false}
                  strokeWidth={2}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="panel">
            <div style={{ fontWeight: 700, marginBlockEnd: "0.5rem" }}>{UI_TEXT.alerts[locale]}</div>
            <div className="stack">
              {alerts.map((a) => (
                <div key={a.alert_id} className="row space-between" style={{ fontSize: "0.9rem" }}>
                  <span style={{ color: SEVERITY_COLOR[a.severity] ?? "inherit" }}>
                    {renderSafe(
                      {
                        cause: a.cause,
                        severity: a.severity,
                        audience: "dispatcher",
                        locale,
                        evidence: a.payload.evidence,
                        ctx: { vehicle: a.device_id },
                      },
                      a.payload.message,
                    )}
                  </span>
                  <span className="muted">{a.ack_ts ? UI_TEXT.acked[locale] : UI_TEXT.pending[locale]}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
