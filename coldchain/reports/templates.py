"""Certificate-specific string table (fr, en).

shared/messages.py already carries the per-cause instruction sentences and
severity labels used elsewhere in the product; this module does not
duplicate those. It adds only what shared/messages.py has no reason to
carry itself: certificate section headers, table column headers, verdict
headline wording, and short noun-phrase labels for the enums the event log
displays as data (cause, prescribed action, driver-stated cause, outcome) --
as opposed to shared/messages.py's own full instruction sentences, which are
written for a driver mid-alert, not a quality officer reading a finished
record.

Arabic ("ar") is a known, stated gap, not a silently broken layout: ReportLab
has no built-in bidi/shaping support, and a certificate that mis-renders
Arabic text (reversed word order, disconnected letterforms) is worse for a
compliance document than one that plainly says the language isn't offered
yet. CERT_LOCALES is ("fr", "en") only; reports/certificate.py rejects "ar"
explicitly with that explanation rather than emitting broken RTL.
"""

from __future__ import annotations

from models.m3_mkt import Verdict
from shared.enums import DriverCause, FaultCause, Outcome, PrescribedAction

CERT_LOCALES: tuple[str, ...] = ("fr", "en")

VERDICT_LABEL: dict[Verdict, dict[str, str]] = {
    Verdict.compliant: {"fr": "CONFORME", "en": "COMPLIANT"},
    Verdict.minor_deviation: {"fr": "DÉVIATION MINEURE", "en": "MINOR DEVIATION"},
    Verdict.excursion_review: {
        "fr": "EXCURSION — REVUE REQUISE",
        "en": "EXCURSION — REVIEW REQUIRED",
    },
}

# RGB, 0-1 (ReportLab's own convention). Colour is a secondary cue only --
# VERDICT_LABEL's word is what actually carries the verdict, so a
# colour-blind reader or a black-and-white photocopy still reads it
# correctly.
VERDICT_COLOR: dict[Verdict, tuple[float, float, float]] = {
    Verdict.compliant: (0.09, 0.45, 0.19),
    Verdict.minor_deviation: (0.72, 0.45, 0.0),
    Verdict.excursion_review: (0.65, 0.08, 0.08),
}

CAUSE_LABEL: dict[FaultCause, dict[str, str]] = {
    FaultCause.bearing_wear: {"fr": "Usure des roulements", "en": "Bearing wear"},
    FaultCause.refrigerant_loss: {"fr": "Perte de frigorigène", "en": "Refrigerant loss"},
    FaultCause.short_cycling: {"fr": "Cycles courts", "en": "Short cycling"},
    FaultCause.fan_failure: {"fr": "Panne de ventilateur", "en": "Fan failure"},
    FaultCause.voltage_sag: {"fr": "Chute de tension", "en": "Voltage sag"},
    FaultCause.unit_off: {"fr": "Groupe à l'arrêt", "en": "Unit off"},
    FaultCause.offload_stop: {"fr": "Arrêt de déchargement", "en": "Offload stop"},
    FaultCause.door_unsecured: {"fr": "Porte non sécurisée", "en": "Door unsecured"},
    FaultCause.seal_failure: {"fr": "Défaut d'étanchéité", "en": "Seal failure"},
    FaultCause.freeze_risk: {"fr": "Risque de gel", "en": "Freeze risk"},
    FaultCause.shock_impact: {"fr": "Choc détecté", "en": "Shock impact"},
    FaultCause.light_exposure: {"fr": "Exposition à la lumière", "en": "Light exposure"},
    FaultCause.tag_lost: {"fr": "Sonde perdue", "en": "Probe lost"},
    FaultCause.ambient_strain: {"fr": "Sollicitation ambiante", "en": "Ambient strain"},
    FaultCause.device_degraded: {"fr": "Appareil dégradé", "en": "Device degraded"},
}

ACTION_LABEL: dict[PrescribedAction, dict[str, str]] = {
    PrescribedAction.close_door: {"fr": "Fermer la porte", "en": "Close door"},
    PrescribedAction.secure_door: {"fr": "Sécuriser la porte", "en": "Secure door"},
    PrescribedAction.restart_unit: {"fr": "Redémarrer le groupe", "en": "Restart unit"},
    PrescribedAction.check_electrical: {"fr": "Vérifier l'électrique", "en": "Check electrical"},
    PrescribedAction.inspect_fan: {"fr": "Inspecter le ventilateur", "en": "Inspect fan"},
    PrescribedAction.inspect_seals: {"fr": "Inspecter les joints", "en": "Inspect seals"},
    PrescribedAction.reposition_pallets: {
        "fr": "Repositionner les palettes",
        "en": "Reposition pallets",
    },
    PrescribedAction.precool_now: {"fr": "Pré-refroidir maintenant", "en": "Precool now"},
    PrescribedAction.raise_within_band: {
        "fr": "Remonter dans la plage",
        "en": "Raise within band",
    },
    PrescribedAction.divert_cold_store: {
        "fr": "Dérouter vers un entrepôt froid",
        "en": "Divert to cold store",
    },
    PrescribedAction.call_dispatch: {"fr": "Appeler le répartiteur", "en": "Call dispatch"},
    PrescribedAction.schedule_service: {"fr": "Planifier un entretien", "en": "Schedule service"},
    PrescribedAction.pull_over_then_check: {
        "fr": "S'arrêter puis vérifier",
        "en": "Pull over, then check",
    },
    PrescribedAction.service_device: {"fr": "Entretenir l'appareil", "en": "Service device"},
}

DRIVER_CAUSE_LABEL: dict[DriverCause, dict[str, str]] = {
    DriverCause.offload_stop: {"fr": "Arrêt de déchargement", "en": "Offload stop"},
    DriverCause.door_left_open: {"fr": "Porte laissée ouverte", "en": "Door left open"},
    DriverCause.unit_failure: {"fr": "Panne du groupe", "en": "Unit failure"},
    DriverCause.power_issue: {"fr": "Problème d'alimentation", "en": "Power issue"},
    DriverCause.loading_delay: {"fr": "Retard de chargement", "en": "Loading delay"},
    DriverCause.other: {"fr": "Autre", "en": "Other"},
}

OUTCOME_LABEL: dict[Outcome, dict[str, str]] = {
    Outcome.pending: {"fr": "En attente", "en": "Pending"},
    Outcome.recovered: {"fr": "Rétabli", "en": "Recovered"},
    Outcome.not_recovered: {"fr": "Non rétabli", "en": "Not recovered"},
}

# General labels: section headers, table columns, and everything else
# certificate.py needs that isn't one of the enum tables above.
L: dict[str, dict[str, str]] = {
    "title": {
        "fr": "Certificat de conformité chaîne du froid",
        "en": "Cold Chain Compliance Certificate",
    },
    "shipment": {"fr": "Expédition", "en": "Shipment"},
    "vehicle": {"fr": "Véhicule", "en": "Vehicle"},
    "route": {"fr": "Itinéraire", "en": "Route"},
    "departure": {"fr": "Départ", "en": "Departure"},
    "arrival": {"fr": "Arrivée", "en": "Arrival"},
    "mission_profile": {"fr": "Profil de mission", "en": "Mission profile"},
    "band": {"fr": "Plage acceptable", "en": "Acceptable band"},
    "temperature_record": {"fr": "Relevé de température", "en": "Temperature record"},
    "chart_gap_note": {
        "fr": "Les zones grisées marquent des périodes non observées -- "
        "aucune valeur n'y est interpolée ; les lignes s'interrompent en conséquence.",
        "en": "Shaded regions mark periods that were not observed -- no value "
        "is interpolated across them, and the lines break there accordingly.",
    },
    "summary": {"fr": "Synthèse", "en": "Summary"},
    "mkt": {
        "fr": "Température cinétique moyenne (MKT)",
        "en": "Mean Kinetic Temperature (MKT)",
    },
    "minutes_above": {"fr": "Minutes hors plage (au-dessus)", "en": "Minutes out of band (above)"},
    "minutes_below": {"fr": "Minutes hors plage (au-dessous)", "en": "Minutes out of band (below)"},
    "worst_excursion": {"fr": "Pire excursion", "en": "Worst excursion"},
    "coverage": {"fr": "Couverture des données", "en": "Data coverage"},
    "shock_events": {"fr": "Chocs enregistrés", "en": "Shock events"},
    "peak_shock": {"fr": "Choc maximal", "en": "Peak shock"},
    "light_exposure_total": {
        "fr": "Exposition lumineuse cumulée",
        "en": "Cumulative light exposure",
    },
    "door_events": {"fr": "Ouvertures de porte", "en": "Door events"},
    "event_log": {"fr": "Journal des événements", "en": "Event log"},
    "col_time": {"fr": "Heure", "en": "Time"},
    "col_cause": {"fr": "Cause", "en": "Cause"},
    "col_severity": {"fr": "Gravité", "en": "Severity"},
    "col_evidence": {"fr": "Preuves", "en": "Evidence"},
    "col_action": {"fr": "Action prescrite", "en": "Prescribed action"},
    "col_ack": {"fr": "Accusé à", "en": "Ack. at"},
    "col_driver_cause": {"fr": "Cause déclarée", "en": "Driver-stated cause"},
    "col_action_taken": {"fr": "Action réalisée", "en": "Action taken"},
    "col_outcome": {"fr": "Issue", "en": "Outcome"},
    "col_notes": {"fr": "Remarques", "en": "Notes"},
    "suppression_reason_prefix": {"fr": "Non alarmé : ", "en": "Not alarmed: "},
    "no_events": {"fr": "Aucun événement enregistré.", "en": "No events recorded."},
    "device_attestation": {"fr": "Attestation de l'appareil", "en": "Device attestation"},
    "device_id": {"fr": "Identifiant appareil", "en": "Device ID"},
    "firmware_version": {"fr": "Version micrologiciel", "en": "Firmware version"},
    "calibration_status": {"fr": "Étalonnage", "en": "Calibration"},
    "calibration_date": {"fr": "Date d'étalonnage", "en": "Calibration date"},
    "calibrated": {"fr": "Étalonné", "en": "Calibrated"},
    "packet_count": {"fr": "Paquets reçus", "en": "Packets received"},
    "buffered_packet_count": {"fr": "Paquets mis en tampon", "en": "Buffered packets"},
    "verification_footer": {
        "fr": "Ce certificat est scellé par un hachage SHA-256 calculé sur la "
        "sérialisation canonique des enregistrements sous-jacents (paquets et "
        "alertes). Toute modification de ces enregistrements change ce hachage, "
        "ce qui permet une vérification indépendante que le certificat n'a pas "
        "été altéré depuis sa génération.",
        "en": "This certificate is sealed with a SHA-256 hash computed over the "
        "canonical serialisation of the underlying records (packets and "
        "alerts). Any change to those records changes this hash, which allows "
        "independent verification that the certificate has not been altered "
        "since it was generated.",
    },
    "verification_hash": {
        "fr": "Hachage de vérification (SHA-256)",
        "en": "Verification hash (SHA-256)",
    },
    "generated_at": {"fr": "Généré le", "en": "Generated at"},
    "no_worst_excursion": {"fr": "Aucune", "en": "None"},
}
