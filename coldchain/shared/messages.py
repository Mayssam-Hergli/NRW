"""Localised message catalogue for fault alerts.

Lives in shared/ (not dashboard/ or api/) because the edge firmware needs
the exact same strings offline -- a driver in a dead zone must see the same
sentence a driver with signal would see. AlertRecord stores cause and
evidence, never a rendered string: the sentence is generated at display
time from the reader's own locale, so a French dispatcher and an Arabic
driver looking at the same alert see the same fact in two languages, not
two different alerts.

Arabic (`ar`) is right-to-left. Any UI that renders these strings must set
dir="rtl" on the containing element and use logical CSS properties
(margin-inline-start / padding-inline-end / text-align: start, etc.), never
physical ones like margin-left -- those flip incorrectly under RTL.
"""

from __future__ import annotations

from shared.enums import FaultCause, Severity

LOCALES: tuple[str, ...] = ("fr", "en", "ar")
DEFAULT_LOCALE = "fr"
AUDIENCES: tuple[str, ...] = ("driver", "dispatcher", "report")

DRIVER_MAX_CHARS = 80

# Substrings that must never appear in a driver-facing message, in any
# locale. Dispatcher and report messages are exempt -- those readers want
# the technical vocabulary.
BANNED_DRIVER_JARGON: tuple[str, ...] = (
    "duty cycle",
    "cycle de service",
    "دورة العمل",
    "anomaly score",
    "score d'anomalie",
    "درجة الشذوذ",
    "excursion",
    "انحراف",
)

SEVERITY_LABEL: dict[Severity, dict[str, str]] = {
    Severity.watch: {"fr": "surveillance", "en": "watch", "ar": "مراقبة"},
    Severity.warning: {"fr": "avertissement", "en": "warning", "ar": "تحذير"},
    Severity.critical: {"fr": "critique", "en": "critical", "ar": "حرج"},
}

# Every driver instruction states whether the cargo is safe right now: a
# reassurance at "watch" severity, a countdown otherwise. This clause is
# appended to every cause's driver instruction, so it only needs writing
# once per locale rather than once per (cause, severity) pair.
SAFE_NOW_CLAUSE: dict[str, str] = {
    "fr": "Chargement en sécurité.",
    "en": "Cargo is safe for now.",
    "ar": "الشحنة آمنة حاليًا.",
}
COUNTDOWN_CLAUSE: dict[str, str] = {
    "fr": "Dépassement dans {eta_min:.0f} min.",
    "en": "Limit breach in {eta_min:.0f} min.",
    "ar": "تجاوز الحد خلال {eta_min:.0f} دقيقة.",
}


def safety_clause(severity: Severity) -> dict[str, str]:
    return SAFE_NOW_CLAUSE if severity == Severity.watch else COUNTDOWN_CLAUSE


# Per-cause copy. "driver" is the instruction alone -- the safety/countdown
# clause above is appended to it by render(), not baked in here, since that
# clause depends on severity, not cause. "dispatcher" and "report" carry
# numbers and technical terms freely, per spec, and don't vary by severity
# (severity is available to them as {severity_label} if a template wants
# it).
CAUSE_COPY: dict[FaultCause, dict[str, dict[str, str]]] = {
    FaultCause.bearing_wear: {
        "driver": {
            "fr": "Bruit compresseur inhabituel possible.",
            "en": "Possible unusual compressor noise.",
            "ar": "قد يصدر الضاغط ضوضاء غير معتادة.",
        },
        "dispatcher": {
            "fr": "{vehicle} pic de démarrage +{dev_pp:.0f} pts vs normale. "
            "Prévoir entretien roulement.",
            "en": "{vehicle} startup peak +{dev_pp:.0f} pts vs baseline. "
            "Schedule bearing service.",
            "ar": "{vehicle} ذروة تشغيل الضاغط أعلى بـ {dev_pp:.0f} نقطة عن المعتاد. "
            "حدد صيانة المحامل.",
        },
        "report": {
            "fr": "Usure des roulements du compresseur suspectée (pic de démarrage "
            "anormal). Entretien recommandé.",
            "en": "Compressor bearing wear suspected (abnormal startup peak). "
            "Service recommended.",
            "ar": "يُشتبه في تآكل محامل الضاغط (ذروة تشغيل غير طبيعية). يُنصح بالصيانة.",
        },
    },
    FaultCause.refrigerant_loss: {
        "driver": {
            "fr": "Froid affaibli.",
            "en": "Cooling weakened.",
            "ar": "التبريد ضعيف.",
        },
        "dispatcher": {
            "fr": "{vehicle} charge +{dev_pp:.0f} pts vs normale à {ambient_c:.0f} °C. "
            "Prévoir entretien.",
            "en": "{vehicle} duty +{dev_pp:.0f} pts vs baseline at {ambient_c:.0f} °C. "
            "Schedule service.",
            "ar": "{vehicle} نسبة التشغيل أعلى بـ {dev_pp:.0f} نقطة عن المعتاد عند "
            "{ambient_c:.0f}°م. حدد الصيانة.",
        },
        "report": {
            "fr": "Perte de capacité de refroidissement détectée (charge +{dev_pp:.0f} "
            "pts). Recharge de fluide frigorigène recommandée.",
            "en": "Cooling capacity loss detected (duty +{dev_pp:.0f} pts). "
            "Refrigerant recharge recommended.",
            "ar": "تم رصد فقدان في سعة التبريد (زيادة {dev_pp:.0f} نقطة). "
            "يُنصح بإعادة شحن غاز التبريد.",
        },
    },
    FaultCause.short_cycling: {
        "driver": {
            "fr": "Fonctionnement irrégulier du groupe.",
            "en": "Unit cycling irregularly.",
            "ar": "تشغيل الوحدة غير منتظم.",
        },
        "dispatcher": {
            "fr": "{vehicle} cycles compresseur rapprochés ({mins:.0f} min). Risque de panne.",
            "en": "{vehicle} compressor short-cycling ({mins:.0f} min intervals). Failure risk.",
            "ar": "{vehicle} تشغيل الضاغط متقطع كل {mins:.0f} دقيقة. خطر عطل.",
        },
        "report": {
            "fr": "Cycles courts du compresseur constatés (intervalle moyen {mins:.0f} "
            "min). Contrôle électrique requis.",
            "en": "Compressor short-cycling observed (average interval {mins:.0f} min). "
            "Electrical check required.",
            "ar": "لوحظ تشغيل متقطع للضاغط (متوسط الفاصل {mins:.0f} دقيقة). يلزم فحص كهربائي.",
        },
    },
    FaultCause.fan_failure: {
        "driver": {
            "fr": "Ventilateur en panne possible.",
            "en": "Possible fan failure.",
            "ar": "احتمال عطل في المروحة.",
        },
        "dispatcher": {
            "fr": "{vehicle} courant ventilateur nul. Vérifier au dépôt.",
            "en": "{vehicle} fan current at zero. Check at depot.",
            "ar": "{vehicle} تيار المروحة صفر. تحقق في المستودع.",
        },
        "report": {
            "fr": "Panne de ventilateur détectée (courant nul). Remplacement recommandé.",
            "en": "Fan failure detected (zero current). Replacement recommended.",
            "ar": "تم رصد عطل في المروحة (تيار صفري). يُنصح بالاستبدال.",
        },
    },
    FaultCause.voltage_sag: {
        "driver": {
            "fr": "Tension électrique faible.",
            "en": "Low electrical voltage.",
            "ar": "انخفاض في الجهد الكهربائي.",
        },
        "dispatcher": {
            "fr": "{vehicle} tension bus {v_bus:.1f} V, sous le seuil. Vérifier alternateur.",
            "en": "{vehicle} bus voltage {v_bus:.1f} V, below threshold. Check alternator.",
            "ar": "{vehicle} جهد الناقل {v_bus:.1f} فولت، أقل من الحد. تحقق من المولد.",
        },
        "report": {
            "fr": "Chute de tension détectée ({v_bus:.1f} V). Alternateur à contrôler.",
            "en": "Voltage sag detected ({v_bus:.1f} V). Alternator to be checked.",
            "ar": "تم رصد انخفاض في الجهد ({v_bus:.1f} فولت). يجب فحص المولد.",
        },
    },
    FaultCause.unit_off: {
        "driver": {
            "fr": "Le froid s'est arrêté.",
            "en": "Cooling has stopped.",
            "ar": "توقف التبريد.",
        },
        "dispatcher": {
            "fr": "{vehicle} compresseur sans courant depuis {mins:.0f} min.",
            "en": "{vehicle} compressor unpowered for {mins:.0f} min.",
            "ar": "{vehicle} الضاغط بدون كهرباء منذ {mins:.0f} دقيقة.",
        },
        "report": {
            "fr": "Arrêt du groupe frigorifique constaté ({mins:.0f} min). Cause à déterminer.",
            "en": "Refrigeration unit shutdown observed ({mins:.0f} min). "
            "Cause to be determined.",
            "ar": "تم رصد توقف وحدة التبريد لمدة {mins:.0f} دقيقة. السبب قيد التحديد.",
        },
    },
    FaultCause.offload_stop: {
        "driver": {
            "fr": "Arrêt prolongé détecté.",
            "en": "Extended stop detected.",
            "ar": "تم رصد توقف طويل.",
        },
        "dispatcher": {
            "fr": "{vehicle} arrêté {mins:.0f} min à {place}. Confirmer déchargement.",
            "en": "{vehicle} stopped {mins:.0f} min at {place}. Confirm offload.",
            "ar": "{vehicle} متوقفة منذ {mins:.0f} دقيقة في {place}. تأكيد التفريغ.",
        },
        "report": {
            "fr": "Arrêt de {mins:.0f} min enregistré à {place}, motif déclaré : déchargement.",
            "en": "{mins:.0f}-minute stop recorded at {place}, stated reason: offload.",
            "ar": "تم تسجيل توقف لمدة {mins:.0f} دقيقة في {place}، السبب المعلن: تفريغ.",
        },
    },
    FaultCause.door_unsecured: {
        "driver": {
            "fr": "Fermez la porte arrière.",
            "en": "Close the rear door.",
            "ar": "أغلق الباب الخلفي.",
        },
        "dispatcher": {
            "fr": "{vehicle} porte ouverte {mins:.0f} min, chargement {temp_c:.1f} °C, en hausse",
            "en": "{vehicle} door open {mins:.0f} min, cargo {temp_c:.1f} °C, rising",
            "ar": "{vehicle} الباب مفتوح منذ {mins:.0f} دقيقة، درجة حرارة الشحنة "
            "{temp_c:.1f}°م، في ارتفاع",
        },
        "report": {
            "fr": "Porte arrière restée ouverte {mins:.0f} min à {place}. "
            "Température atteinte {temp_c:.1f} °C.",
            "en": "Rear door left open for {mins:.0f} min at {place}. "
            "Temperature reached {temp_c:.1f} °C.",
            "ar": "بقي الباب الخلفي مفتوحًا لمدة {mins:.0f} دقيقة في {place}. "
            "بلغت الحرارة {temp_c:.1f}°م.",
        },
    },
    FaultCause.seal_failure: {
        "driver": {
            "fr": "Étanchéité de porte à vérifier.",
            "en": "Door seal needs checking.",
            "ar": "يلزم فحص إحكام غلق الباب.",
        },
        "dispatcher": {
            "fr": "{vehicle} joint de porte suspect, {temp_c:.1f} °C au point le plus chaud.",
            "en": "{vehicle} suspect door seal, {temp_c:.1f} °C at warmest point.",
            "ar": "{vehicle} يُشتبه بعطل في حشية الباب، {temp_c:.1f}°م عند أعلى نقطة حرارة.",
        },
        "report": {
            "fr": "Défaut d'étanchéité de porte suspecté (écart thermique localisé). "
            "Contrôle du joint recommandé.",
            "en": "Door seal defect suspected (localized thermal gap). "
            "Seal inspection recommended.",
            "ar": "يُشتبه في عيب بحشية الباب (فارق حراري موضعي). يُنصح بفحص الحشية.",
        },
    },
    FaultCause.freeze_risk: {
        "driver": {
            "fr": "Chargement trop froid.",
            "en": "Cargo too cold.",
            "ar": "الشحنة باردة جدًا.",
        },
        "dispatcher": {
            "fr": "{vehicle} approche limite basse ({temp_c:.1f} °C), charge sensible au gel.",
            "en": "{vehicle} nearing lower limit ({temp_c:.1f} °C), freeze-sensitive load.",
            "ar": "{vehicle} تقترب من الحد الأدنى ({temp_c:.1f}°م)، شحنة حساسة للتجمد.",
        },
        "report": {
            "fr": "Approche du seuil de gel constatée ({temp_c:.1f} °C). Réglage à vérifier.",
            "en": "Approach to freeze threshold observed ({temp_c:.1f} °C). "
            "Setpoint to be checked.",
            "ar": "لوحظ اقتراب من حد التجمد ({temp_c:.1f}°م). يجب مراجعة الإعداد.",
        },
    },
    FaultCause.shock_impact: {
        "driver": {
            "fr": "Choc détecté sur le chargement.",
            "en": "Impact detected on cargo.",
            "ar": "تم رصد صدمة في الشحنة.",
        },
        "dispatcher": {
            "fr": "{vehicle} choc de {peak_g:.1f} g détecté à {place}.",
            "en": "{vehicle} {peak_g:.1f} g impact detected at {place}.",
            "ar": "{vehicle} تم رصد صدمة بقوة {peak_g:.1f} g في {place}.",
        },
        "report": {
            "fr": "Choc de {peak_g:.1f} g enregistré à {place}. "
            "Inspection du chargement recommandée.",
            "en": "{peak_g:.1f} g impact recorded at {place}. Cargo inspection recommended.",
            "ar": "تم تسجيل صدمة بقوة {peak_g:.1f} g في {place}. يُنصح بفحص الشحنة.",
        },
    },
    FaultCause.light_exposure: {
        "driver": {
            "fr": "Exposition à la lumière détectée.",
            "en": "Light exposure detected.",
            "ar": "تم رصد تعرض للضوء.",
        },
        "dispatcher": {
            "fr": "{vehicle} exposition lumière {mins:.0f} min, seuil profil dépassé.",
            "en": "{vehicle} light exposure {mins:.0f} min, profile limit exceeded.",
            "ar": "{vehicle} تعرض للضوء لمدة {mins:.0f} دقيقة، تجاوز حد الملف.",
        },
        "report": {
            "fr": "Exposition à la lumière de {mins:.0f} min enregistrée, "
            "au-delà du seuil autorisé.",
            "en": "{mins:.0f}-minute light exposure recorded, beyond the allowed threshold.",
            "ar": "تم تسجيل تعرض للضوء لمدة {mins:.0f} دقيقة، تجاوز الحد المسموح.",
        },
    },
    FaultCause.tag_lost: {
        "driver": {
            "fr": "Capteur de température déconnecté.",
            "en": "Temperature sensor disconnected.",
            "ar": "انقطع اتصال حساس الحرارة.",
        },
        "dispatcher": {
            "fr": "{vehicle} sonde {place} muette depuis {mins:.0f} min.",
            "en": "{vehicle} {place} probe silent for {mins:.0f} min.",
            "ar": "{vehicle} مسبار {place} صامت منذ {mins:.0f} دقيقة.",
        },
        "report": {
            "fr": "Perte de communication avec la sonde {place} pendant {mins:.0f} min.",
            "en": "Communication lost with the {place} probe for {mins:.0f} min.",
            "ar": "انقطع الاتصال بمسبار {place} لمدة {mins:.0f} دقيقة.",
        },
    },
    FaultCause.ambient_strain: {
        "driver": {
            "fr": "Chaleur extérieure élevée.",
            "en": "High outside heat.",
            "ar": "حرارة خارجية مرتفعة.",
        },
        "dispatcher": {
            "fr": "{vehicle} ambiante {ambient_c:.0f} °C, groupe sollicité au maximum.",
            "en": "{vehicle} ambient {ambient_c:.0f} °C, unit under maximum strain.",
            "ar": "{vehicle} الحرارة المحيطة {ambient_c:.0f}°م، الوحدة تحت أقصى ضغط.",
        },
        "report": {
            "fr": "Sollicitation maximale du groupe sous forte chaleur ambiante "
            "({ambient_c:.0f} °C).",
            "en": "Unit under maximum strain in high ambient heat ({ambient_c:.0f} °C).",
            "ar": "الوحدة تحت أقصى ضغط بسبب ارتفاع الحرارة المحيطة ({ambient_c:.0f}°م).",
        },
    },
    FaultCause.device_degraded: {
        "driver": {
            "fr": "Appareil de suivi à vérifier.",
            "en": "Tracking device needs checking.",
            "ar": "يلزم فحص جهاز التتبع.",
        },
        "dispatcher": {
            "fr": "{vehicle} santé appareil dégradée, signal ou batterie faible.",
            "en": "{vehicle} device health degraded, weak signal or battery.",
            "ar": "{vehicle} تدهور حالة الجهاز، إشارة أو بطارية ضعيفة.",
        },
        "report": {
            "fr": "Dégradation de l'état de l'appareil de suivi constatée pendant le trajet.",
            "en": "Tracking device health degradation observed during transit.",
            "ar": "لوحظ تدهور في حالة جهاز التتبع أثناء الرحلة.",
        },
    },
}


def render(
    cause: FaultCause,
    severity: Severity,
    audience: str,
    locale: str,
    evidence: dict[str, float] | None = None,
    **ctx: object,
) -> str:
    """Render a fault alert for one (cause, severity, audience, locale).

    `evidence` and `**ctx` are merged (ctx wins on collision) into the
    named placeholders the cause's template uses. A placeholder the caller
    didn't supply raises KeyError immediately -- never silently drops into
    a half-empty sentence.
    """
    if locale not in LOCALES:
        raise ValueError(f"unknown locale: {locale!r}")
    if audience not in AUDIENCES:
        raise ValueError(f"unknown audience: {audience!r}")
    if cause not in CAUSE_COPY:
        raise ValueError(f"no message copy for cause: {cause!r}")

    merged: dict[str, object] = {**(evidence or {}), **ctx}
    merged.setdefault("severity_label", SEVERITY_LABEL[severity][locale])

    if audience == "driver":
        instruction = CAUSE_COPY[cause]["driver"][locale]
        clause = safety_clause(severity)[locale]
        template = f"{instruction} {clause}"
    else:
        template = CAUSE_COPY[cause][audience][locale]

    try:
        return template.format(**merged)
    except KeyError as exc:
        raise KeyError(
            f"missing placeholder {exc} rendering {cause}/{severity}/{audience}/{locale}"
        ) from exc
