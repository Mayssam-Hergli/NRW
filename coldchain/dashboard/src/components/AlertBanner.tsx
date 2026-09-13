import { useId, useState } from "react";
import { useAlerts } from "../hooks/useAlerts";
import { messages } from "../i18n/messages";
import type { AlertRow, DriverCause, Locale, PrescribedAction } from "../lib/types";

const DRIVER_CAUSE_LABEL: Record<DriverCause, Record<Locale, string>> = {
  offload_stop: { fr: "Déchargement", en: "Unloading", ar: "تفريغ" },
  door_left_open: { fr: "Porte ouverte", en: "Door left open", ar: "الباب مفتوح" },
  unit_failure: { fr: "Panne du groupe", en: "Unit failure", ar: "عطل التبريد" },
  power_issue: { fr: "Problème électrique", en: "Power issue", ar: "مشكلة كهربائية" },
  loading_delay: { fr: "Retard de chargement", en: "Loading delay", ar: "تأخر التحميل" },
  other: { fr: "Autre", en: "Other", ar: "أخرى" },
};

const ACTIONS: Record<PrescribedAction, [string, string, string]> = {
  close_door: ["Fermez la porte.", "Close the door.", "أغلق الباب."],
  secure_door: ["Vérifiez la fermeture de la porte.", "Check that the door is secured.", "تحقق من إحكام إغلاق الباب."],
  restart_unit: ["Vérifiez et redémarrez le groupe selon la procédure.", "Check and restart the unit following your procedure.", "افحص الوحدة وأعد تشغيلها وفق الإجراءات."],
  check_electrical: ["Faites vérifier l’alimentation électrique.", "Arrange an electrical supply check.", "اطلب فحص مصدر الكهرباء."],
  inspect_fan: ["Faites vérifier le ventilateur.", "Arrange a fan inspection.", "اطلب فحص المروحة."],
  inspect_seals: ["Vérifiez les joints de porte à l’arrêt.", "Check the door seals when stopped.", "افحص أختام الباب عند التوقف."],
  reposition_pallets: ["Vérifiez la circulation d’air autour des palettes.", "Check airflow around the pallets.", "تحقق من تدفق الهواء حول المنصات."],
  precool_now: ["Lancez le prérefroidissement selon la procédure.", "Start precooling following your procedure.", "ابدأ التبريد المسبق وفق الإجراءات."],
  raise_within_band: ["Ajustez la consigne dans la plage autorisée.", "Adjust the setpoint within the permitted band.", "اضبط الحرارة ضمن النطاق المسموح."],
  divert_cold_store: ["Contactez la régulation pour un dépôt frigorifique.", "Contact dispatch to arrange cold storage.", "اتصل بالتنسيق لترتيب التخزين المبرد."],
  call_dispatch: ["Contactez la régulation.", "Contact dispatch.", "اتصل بالتنسيق."],
  schedule_service: ["Prévenez la régulation pour organiser une maintenance.", "Notify dispatch to arrange maintenance.", "أبلغ التنسيق لترتيب الصيانة."],
  pull_over_then_check: ["Arrêtez-vous en sécurité, puis vérifiez.", "Pull over safely, then check.", "توقف بأمان، ثم تحقق."],
  service_device: ["Signalez le problème de l’appareil à la régulation.", "Report the device issue to dispatch.", "أبلغ التنسيق بمشكلة الجهاز."],
};

// Use the cause instruction without the catalogue's blanket “cargo safe”
// clause: a stored alert cannot establish the current cargo condition.
export function driverAlertText(alert: AlertRow, locale: Locale) {
  return messages.causeCopy[alert.cause]?.driver[locale] ?? alert.payload.message;
}

export function AlertBanner({ alert, locale }: { alert: AlertRow; locale: Locale }) {
  const { acknowledge } = useAlerts(alert.device_id);
  const t = (fr: string, en: string, ar: string) => ({ fr, en, ar })[locale];
  const [acknowledged, setAcknowledged] = useState(Boolean(alert.ack_ts));
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);
  const [selectedCause, setSelectedCause] = useState<DriverCause | null>(alert.driver_cause);
  const [actionTaken, setActionTaken] = useState(alert.action_taken ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const inputId = useId();
  const seen = acknowledged || Boolean(alert.ack_ts);
  const hasResponse = saved || Boolean(alert.driver_cause || alert.action_taken);
  const action = ACTIONS[alert.payload.prescribed_action];

  async function submit(response: boolean) {
    setBusy(true); setError(false);
    try {
      await acknowledge(alert.alert_id, response ? { driverCause: selectedCause ?? undefined, actionTaken: actionTaken.trim() || undefined, outcome: "pending" } : {});
      setAcknowledged(true);
      setEditing(!response);
      if (response) setSaved(true);
    } catch { setError(true); }
    finally { setBusy(false); }
  }

  return <section className={`driver-alert driver-alert--${alert.severity}`} aria-label={t("Alerte à suivre", "Alert to follow up", "تنبيه للمتابعة")}>
    <div className="driver-alert-heading">
      <span className="driver-alert-level">{messages.severityLabel[alert.severity][locale]}</span>
      <time dateTime={alert.issued_ts}>{new Date(alert.issued_ts).toLocaleString(locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</time>
    </div>
    <h2>{driverAlertText(alert, locale)}</h2>
    {action && <p className="driver-alert-action">{t(...action)}</p>}
    <div className="driver-alert-controls">
      {!seen ? <button disabled={busy} onClick={() => void submit(false)}>{busy ? t("Envoi…", "Sending…", "جارٍ الإرسال…") : t("J’ai vu l’alerte", "Acknowledge alert", "تم الاطلاع على التنبيه")}</button>
        : <><span className="driver-response-status">✓ {t("Vue · suivi en cours", "Acknowledged · follow-up open", "تم الاطلاع · المتابعة مستمرة")}</span>
          {!editing && <button className="secondary" onClick={() => setEditing(true)}>{hasResponse ? t("Modifier mon retour", "Edit my response", "تعديل ردي") : t("Ajouter mon retour", "Add my response", "إضافة ردي")}</button>}</>}
    </div>
    {hasResponse && !editing && <p className="driver-response-note" role="status">{t("Retour enregistré. L’alerte reste ouverte jusqu’à sa résolution.", "Response recorded. This alert stays open until resolved.", "تم تسجيل الرد. يبقى التنبيه مفتوحًا حتى الحل.")}</p>}
    {editing && <form className="driver-response-form" onSubmit={e => { e.preventDefault(); void submit(true); }}>
      <fieldset disabled={busy}>
        <legend>{t("Qu’avez-vous constaté ?", "What did you find?", "ماذا لاحظت؟")}</legend>
        <div className="driver-cause-grid">{(Object.keys(DRIVER_CAUSE_LABEL) as DriverCause[]).map(cause => <button className="secondary" type="button" key={cause} aria-pressed={selectedCause === cause} onClick={() => setSelectedCause(cause)}>{DRIVER_CAUSE_LABEL[cause][locale]}</button>)}</div>
        <label htmlFor={inputId}>{t("Action effectuée (facultatif)", "Action taken (optional)", "الإجراء المتخذ (اختياري)")}</label>
        <textarea id={inputId} rows={2} maxLength={500} value={actionTaken} onChange={e => setActionTaken(e.target.value)} placeholder={t("Ex. Porte refermée et groupe vérifié.", "E.g. Closed the door and checked the unit.", "مثال: أغلقت الباب وفحصت الوحدة.")} />
        <div className="row"><button disabled={!selectedCause || busy} type="submit">{busy ? t("Enregistrement…", "Saving…", "جارٍ الحفظ…") : t("Enregistrer mon retour", "Save response", "حفظ الرد")}</button><button className="secondary" type="button" onClick={() => setEditing(false)}>{t("Plus tard", "Later", "لاحقًا")}</button></div>
      </fieldset>
    </form>}
    {error && <p className="error-text" role="alert">{t("Envoi impossible. Votre retour n’est pas enregistré. Réessayez.", "Could not send. Your response was not saved. Please retry.", "تعذر الإرسال. لم يُحفظ ردك. أعد المحاولة.")}</p>}
  </section>;
}
