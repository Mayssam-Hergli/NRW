import { useEffect, useState } from "react";
import { AlertBanner, driverAlertText } from "../components/AlertBanner";
import { AppHeader } from "../components/AppHeader";
import { BandIndicator } from "../components/BandIndicator";
import { DriverHistory } from "../components/DriverHistory";
import { useAlerts } from "../hooks/useAlerts";
import { useFleet } from "../hooks/useFleet";
import { useTelemetryHistory } from "../hooks/useTelemetryHistory";
import { useAuth } from "../lib/auth";
import type { Locale, MissionProfile, ProbePosition } from "../lib/types";

const ACTIVE_STATES = new Set(["watch", "warning", "critical", "escalated", "acknowledged"]);
const PROBE_POSITION: Record<ProbePosition, [string, string, string]> = {
  front: ["Avant", "Front", "الأمام"], rear_door: ["Porte arrière", "Rear door", "الباب الخلفي"],
  top: ["Haut", "Top", "الأعلى"], bottom: ["Bas", "Bottom", "الأسفل"], ambient_external: ["Extérieur", "Outside", "الخارج"],
};
const PROFILES: Record<MissionProfile, [string, string, string]> = {
  pharma_refrigerated: ["Produits pharmaceutiques réfrigérés", "Refrigerated pharmaceuticals", "مستحضرات دوائية مبردة"],
  pharma_frozen: ["Produits pharmaceutiques congelés", "Frozen pharmaceuticals", "مستحضرات دوائية مجمدة"],
  controlled_room_temp: ["Température ambiante contrôlée", "Controlled room temperature", "درجة حرارة الغرفة المضبوطة"],
  vaccines: ["Vaccins", "Vaccines", "لقاحات"], fresh_produce: ["Produits frais", "Fresh produce", "منتجات طازجة"],
};

export function DriverView({ locale }: { locale: Locale }) {
  const { profile, signOut } = useAuth();
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [focusMode, setFocusMode] = useState(false);
  const [now, setNow] = useState(Date.now);
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState(false);
  const [sending, setSending] = useState(false);
  const [ackError, setAckError] = useState(false);
  const [seenAlertId, setSeenAlertId] = useState<string | null>(null);
  const t = (fr: string, en: string, ar: string) => ({ fr, en, ar })[locale];
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(timer); }, []);

  const fleet = useFleet();
  const { entries } = fleet;
  // Fleet order follows urgency. Pin the initial selection so another truck's
  // new alert cannot silently switch the vehicle a driver is watching.
  const deviceId = selectedDevice ?? entries[0]?.deviceId ?? null;
  useEffect(() => { if (!selectedDevice && deviceId) setSelectedDevice(deviceId); }, [deviceId, selectedDevice]);
  const telemetry = useTelemetryHistory(deviceId);
  const alertFeed = useAlerts(deviceId);
  const { acknowledge } = alertFeed;
  const packets = telemetry.packets.filter(p => p.device_id === deviceId);
  const alerts = alertFeed.alerts.filter(a => a.device_id === deviceId);
  const latest = packets[packets.length - 1];
  const activeAlerts = alerts.filter(a => ACTIVE_STATES.has(a.state)).sort((a, b) => ({ critical: 3, warning: 2, watch: 1 }[b.severity] - { critical: 3, warning: 2, watch: 1 }[a.severity]) || Date.parse(b.issued_ts) - Date.parse(a.issued_ts));
  const activeAlert = activeAlerts[0];
  const connection = telemetry.connection === "disconnected" || fleet.connection === "disconnected" ? "disconnected" : telemetry.connection;
  const vehicleSelect = <div className="driver-vehicle-picker"><label htmlFor="driver-vehicle">{t("Véhicule à suivre", "Vehicle to follow", "المركبة المتابعة")}</label><select id="driver-vehicle" value={deviceId ?? ""} onChange={e => { setSelectedDevice(e.target.value); setFocusMode(false); }}>
    {deviceId && !entries.some(e => e.deviceId === deviceId) && <option value={deviceId}>{deviceId}</option>}
    {entries.map(e => <option key={e.deviceId} value={e.deviceId}>{e.deviceId}</option>)}
  </select></div>;

  if (!deviceId || !latest) {
    const loading = fleet.loading || telemetry.loading;
    const error = fleet.error || telemetry.error;
    return <div><AppHeader connection={fleet.connection} locale={locale} /><main className="page driver-workspace stack">
      <div className="driver-page-heading"><div><span className="eyebrow">{t("ESPACE CHAUFFEUR", "DRIVER WORKSPACE", "مساحة السائق")}</span><h1>{t("Votre trajet", "Your journey", "رحلتك")}</h1></div>{entries.length > 0 && vehicleSelect}</div>
      <section className="panel driver-empty" role="status"><span className="driver-empty-icon" aria-hidden="true">↔</span><h2>{loading ? t("Chargement des mesures…", "Loading readings…", "جارٍ تحميل القراءات…") : error ? t("Mesures indisponibles", "Readings unavailable", "القراءات غير متاحة") : t("En attente de votre véhicule", "Waiting for your vehicle", "بانتظار مركبتك")}</h2><p>{error ? t("La connexion aux données a échoué. Réessayez pour récupérer les mesures.", "We could not load your readings. Retry to reconnect.", "تعذر تحميل القراءات. أعد المحاولة للاتصال.") : t("Les mesures apparaîtront dès qu’un véhicule transmettra ses données. Vérifiez le véhicule à suivre avec la régulation.", "Readings will appear when a vehicle sends data. Confirm the vehicle to follow with dispatch.", "ستظهر القراءات عندما ترسل مركبة بياناتها. تحقق من المركبة المتابعة مع التنسيق.")}</p>{!loading && <button className="secondary" onClick={() => { fleet.retry?.(); telemetry.retry?.(); }}>{t("Réessayer", "Retry", "إعادة المحاولة")}</button>}</section>
    </main></div>;
  }

  const probes = latest.cargo.filter(c => c.pos !== "ambient_external" && Number.isFinite(c.t_c));
  const coldest = probes.length ? Math.min(...probes.map(c => c.t_c)) : null;
  const hottest = probes.length ? Math.max(...probes.map(c => c.t_c)) : null;
  const band = latest.band && latest.band.max_c > latest.band.min_c ? latest.band : null;
  const worst = coldest != null && band && coldest < band.min_c ? coldest : hottest;
  const ageMs = now - Date.parse(latest.ts);
  const timestampValid = Number.isFinite(ageMs) && ageMs >= -60000;
  const ageMin = timestampValid ? Math.max(0, Math.floor(ageMs / 60000)) : null;
  const stale = ageMin == null || ageMin >= 5;
  const outside = Boolean(band && coldest != null && hottest != null && (coldest < band.min_c || hottest > band.max_c));
  const moving = latest.gnss.fix !== "NONE" && latest.gnss.speed_kmh > 0;
  const movementKnown = latest.gnss.fix !== "NONE" && Number.isFinite(latest.gnss.speed_kmh) && !stale;
  const driving = moving || focusMode;
  const status = stale ? t("Readings are stale", "Readings are stale", "قراءات قديمة") : !probes.length ? t("Mesure du chargement indisponible", "Cargo reading unavailable", "قراءة الشحنة غير متاحة") : outside ? t("Température hors plage", "Temperature outside band", "الحرارة خارج النطاق") : activeAlert ? t("Vérification nécessaire", "Check required", "يلزم التحقق") : band ? t("Température dans la plage", "Temperature within band", "الحرارة ضمن النطاق") : t("Plage non définie", "No temperature band set", "نطاق الحرارة غير محدد");
  const attention = stale || outside || !probes.length || !band || Boolean(activeAlert) || Boolean(telemetry.error);
  const unit = ({ RUN: ["Groupe en marche", "Unit running", "الوحدة تعمل"], OFF: ["Groupe à l’arrêt", "Unit off", "الوحدة متوقفة"], SHORT_CYCLE: ["Cycles courts", "Short cycling", "دورات قصيرة"], FAULT: ["Panne du groupe", "Unit fault", "عطل بالوحدة"] } as const)[latest.power.state];
  const freshness = timestampValid ? `${new Date(latest.ts).toLocaleString(locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · ${ageMin! < 1 ? t("il y a moins d’une minute", "less than a minute ago", "منذ أقل من دقيقة") : `${ageMin} min`}` : t("Horodatage invalide", "Invalid reading time", "وقت القراءة غير صالح");
  const nextStep = stale || telemetry.error ? t("L’état actuel n’est pas confirmé. À l’arrêt, vérifiez le groupe et la connexion du boîtier.", "Current conditions are unconfirmed. When stopped, check the unit and the device connection.", "الحالة الحالية غير مؤكدة. عند التوقف، افحص الوحدة واتصال الجهاز.") : !probes.length ? t("Vérifiez les sondes et prévenez la régulation.", "Check the probes and notify dispatch.", "افحص المجسات وأبلغ التنسيق.") : outside ? t("À l’arrêt, vérifiez la porte et le groupe froid. Prévenez la régulation si la température ne revient pas dans la plage.", "When stopped, check the door and refrigeration unit. Notify dispatch if the temperature does not return to band.", "عند التوقف، افحص الباب ووحدة التبريد. أبلغ التنسيق إذا لم تعد الحرارة للنطاق.") : !band ? t("Faites confirmer la plage requise pour cette expédition par la régulation.", "Ask dispatch to confirm this shipment’s required temperature band.", "اطلب من التنسيق تأكيد نطاق الحرارة المطلوب للشحنة.") : activeAlert ? t("Consultez l’alerte et enregistrez votre retour à l’arrêt.", "Review the alert and record your response when stopped.", "راجع التنبيه وسجّل ردك عند التوقف.") : latest.door.open ? t("Porte ouverte. Refermez-la dès la fin du chargement ou du déchargement.", "Door open. Close it when loading or unloading is complete.", "الباب مفتوح. أغلقه عند انتهاء التحميل أو التفريغ.") : t("Surveillez les prochaines mesures et gardez la porte fermée pendant le trajet.", "Monitor incoming readings and keep the door closed during transport.", "تابع القراءات القادمة وأبقِ الباب مغلقًا أثناء النقل.");

  if (driving) return <main className="page driver-focus stack">
    <div className="driver-focus-toolbar"><span className="driver-mode">{t("MODE CONDUITE", "DRIVING MODE", "وضع القيادة")}</span><button className="secondary" disabled={loggingOut} onClick={async () => { setLoggingOut(true); setLogoutError(false); try { await signOut(); } catch { setLogoutError(true); } finally { setLoggingOut(false); } }}>{loggingOut ? t("Déconnexion…", "Signing out…", "جارٍ الخروج…") : t("Se déconnecter", "Log out", "تسجيل الخروج")}</button></div>
    {logoutError && <p role="alert">{t("Déconnexion impossible. Réessayez.", "Could not sign out. Please retry.", "تعذر الخروج. أعد المحاولة.")}</p>}
    <div className="driver-focus-identity"><h1>{deviceId}</h1><span>{latest.shipment_id ?? t("Expédition non renseignée", "No shipment linked", "لا توجد شحنة مرتبطة")}</span></div>
    <section className={`panel driver-focus-reading ${attention ? "needs-attention" : ""}`}><BandIndicator currentC={worst} band={band} locale={locale} stale={stale} /><p className="driver-focus-status">{status}</p><p className="driver-freshness">{freshness}</p></section>
    {activeAlert ? <section className={`driver-alert driver-alert--${activeAlert.severity}`}><h2>{activeAlert.severity === "critical" ? t("Arrêtez-vous en sécurité, puis vérifiez.", "Pull over safely, then check.", "توقف بأمان، ثم تحقق.") : driverAlertText(activeAlert, locale)}</h2>{!activeAlert.ack_ts && seenAlertId !== activeAlert.alert_id ? <button disabled={sending} onClick={async () => { setSending(true); setAckError(false); try { await acknowledge(activeAlert.alert_id, {}); setSeenAlertId(activeAlert.alert_id); } catch { setAckError(true); } finally { setSending(false); } }}>{sending ? t("Envoi…", "Sending…", "جارٍ الإرسال…") : t("J’ai vu", "Acknowledge", "تم الاطلاع")}</button> : <p>{t("Alerte vue · suivi à compléter à l’arrêt", "Acknowledged · follow up when stopped", "تم الاطلاع · أكمل المتابعة عند التوقف")}</p>}{ackError && <p role="alert">{t("Envoi impossible. Réessayez à l’arrêt.", "Could not send. Retry when stopped.", "تعذر الإرسال. أعد المحاولة عند التوقف.")}</p>}</section> : <p className="driver-focus-guidance">{nextStep}</p>}
    {stale && activeAlert && <p className="driver-notice">{nextStep}</p>}
    <p className="driver-focus-note">{t("Les détails et le choix du véhicule sont accessibles à l’arrêt.", "Details and vehicle selection are available when stopped.", "التفاصيل واختيار المركبة متاحان عند التوقف.")}</p>
    {!moving && <button className="secondary" onClick={() => setFocusMode(false)}>{t("Afficher les détails", "Show details", "عرض التفاصيل")}</button>}
  </main>;

  return <div><AppHeader connection={connection} locale={locale} /><main className="page driver-workspace stack">
    <header className="driver-page-heading"><div><span className="eyebrow">{t("ESPACE CHAUFFEUR", "DRIVER WORKSPACE", "مساحة السائق")}</span><h1>{t("Votre trajet, l’essentiel", "Your journey, at a glance", "رحلتك، أهم المعلومات")}</h1><p>{profile?.display_name ? `${t("Bonjour", "Hello", "مرحبًا")}, ${profile.display_name}. ` : ""}{t("Le chargement et les actions à suivre.", "Your cargo and what needs your attention.", "شحنتك وما يحتاج إلى انتباهك.")}</p></div><button className="secondary driver-focus-button" onClick={() => setFocusMode(true)}>{t("Mode conduite", "Driving mode", "وضع القيادة")} <span aria-hidden="true">↗</span></button></header>
    <section className="driver-journey-bar">{vehicleSelect}<div className="driver-shipment"><span>{t("Expédition", "Shipment", "الشحنة")}</span><strong>{latest.shipment_id ?? t("Non renseignée", "Not linked", "غير مرتبطة")}</strong></div><span className="driver-mode">{movementKnown ? t("À L’ARRÊT", "STOPPED", "متوقف") : t("MOUVEMENT INCONNU", "MOVEMENT UNKNOWN", "الحركة غير معروفة")}</span></section>
    <div className={`driver-status-strip ${attention ? "needs-attention" : ""}`} role="status"><div><span className="driver-status-dot" aria-hidden="true" /><strong>{status === "Readings are stale" && locale === "fr" ? "Mesures anciennes" : status}</strong></div><span>{t("Dernière mesure", "Last reading", "آخر قراءة")} · {freshness}</span></div>
    {telemetry.error && <div className="driver-notice" role="alert">{t("La mise à jour des mesures a échoué.", "Readings could not be refreshed.", "تعذر تحديث القراءات.")} <button className="secondary" onClick={() => telemetry.retry?.()}>{t("Réessayer", "Retry", "إعادة المحاولة")}</button></div>}
    <div className="driver-main-grid"><section className={`panel driver-cargo-panel ${attention ? "needs-attention" : ""}`}>
      <div className="driver-section-heading"><h2>{t("Température du chargement", "Cargo temperature", "حرارة الشحنة")}</h2><span>{probes.length} {t("sonde(s)", "probe(s)", "مجسات")}</span></div>
      <BandIndicator currentC={worst} band={band} locale={locale} stale={stale} />
      <p className="driver-reading-caption">{t("Sonde la plus froide si sous la limite, sinon la plus chaude.", "Coldest probe if below the limit; otherwise the warmest.", "أبرد مجس إن كان دون الحد؛ وإلا الأدفأ.")}</p>
      <div className="driver-temperature-range"><div><span>{t("Minimum", "Minimum", "الأدنى")}</span><strong>{coldest == null ? "—" : `${coldest.toFixed(1)}°C`}</strong></div><div><span>{t("Maximum", "Maximum", "الأعلى")}</span><strong>{hottest == null ? "—" : `${hottest.toFixed(1)}°C`}</strong></div></div>
      <details className="driver-probe-details"><summary>{t("Voir les sondes", "View probes", "عرض المجسات")}</summary><div className="driver-probe-grid">{probes.map(p => <div key={p.tag} className="driver-probe"><span>{t(PROBE_POSITION[p.pos][0], PROBE_POSITION[p.pos][1], PROBE_POSITION[p.pos][2])} · {p.tag}</span><strong className={band && (p.t_c < band.min_c || p.t_c > band.max_c) ? "attention" : ""}>{p.t_c.toFixed(1)}°C</strong></div>)}</div></details>
    </section><div className="driver-side-column stack">
      <section className={`panel driver-next-step ${attention ? "needs-attention" : ""}`}><span className="eyebrow">{t("VOTRE PROCHAINE ACTION", "YOUR NEXT STEP", "خطوتك التالية")}</span><h2>{attention ? t("Vérifier à l’arrêt", "Check when stopped", "تحقق عند التوقف") : latest.door.open ? t("Porte à refermer", "Close the door after loading", "أغلق الباب بعد التحميل") : t("Poursuivre la surveillance", "Keep monitoring", "واصل المتابعة")}</h2><p>{nextStep}</p></section>
      <section className="panel driver-essentials"><h2>{t("À bord", "On board", "على متن المركبة")}</h2><dl><div><dt>{t("Groupe froid", "Refrigeration", "التبريد")}</dt><dd className={latest.power.state === "FAULT" || latest.power.state === "SHORT_CYCLE" ? "attention" : ""}>{t(unit[0], unit[1], unit[2])}</dd></div><div><dt>{t("Porte", "Door", "الباب")}</dt><dd className={latest.door.open ? "attention" : ""}>{latest.door.open ? t("Ouverte", "Open", "مفتوح") : t("Fermée", "Closed", "مغلق")}</dd></div><div><dt>{t("Extérieur", "Outside", "الخارج")}</dt><dd>{Number.isFinite(latest.ambient_c) ? `${latest.ambient_c.toFixed(1)}°C` : "—"}</dd></div><div><dt>{t("Chargement", "Cargo profile", "نوع الشحنة")}</dt><dd>{latest.mission_profile ? t(PROFILES[latest.mission_profile][0], PROFILES[latest.mission_profile][1], PROFILES[latest.mission_profile][2]) : t("Non renseigné", "Not specified", "غير محدد")}</dd></div></dl>{stale && <p className="insight-note">{t("Dernier état connu, à vérifier.", "Last known state; verify on site.", "آخر حالة معروفة؛ تحقق ميدانيًا.")}</p>}</section>
    </div></div>
    <section className="driver-alert-section"><div className="driver-section-heading"><h2>{t("À suivre", "Needs follow-up", "بحاجة للمتابعة")}</h2><span>{activeAlerts.length} {t("alerte(s) ouverte(s)", "open alert(s)", "تنبيهات مفتوحة")}</span></div>
      {activeAlert ? <><AlertBanner key={activeAlert.alert_id} alert={activeAlert} locale={locale} />{activeAlerts.length > 1 && <details className="panel driver-details"><summary>{t("Autres alertes ouvertes", "Other open alerts", "تنبيهات مفتوحة أخرى")} ({activeAlerts.length - 1})</summary><div className="stack">{activeAlerts.slice(1).map(a => <AlertBanner key={a.alert_id} alert={a} locale={locale} />)}</div></details>}</> : <p className="driver-no-alerts">{t("Aucune alerte ouverte reçue pour ce véhicule.", "No open alerts received for this vehicle.", "لم تصل تنبيهات مفتوحة لهذه المركبة.")}</p>}
    </section>
    <DriverHistory key={deviceId} packets={packets} alerts={alerts} locale={locale} />
    <p className="driver-assignment-note">{t("Le véhicule choisi reste affiché pendant cette session. Ce choix ne modifie pas votre affectation.", "Your selected vehicle stays in view during this session. This does not change your assignment.", "تبقى المركبة المختارة معروضة خلال هذه الجلسة. هذا لا يغير تعيينك.")}</p>
  </main></div>;
}
