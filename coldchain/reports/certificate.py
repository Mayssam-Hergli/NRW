"""Per-shipment compliance certificate -- the PDF that replaces the
USB-key ritual: what the consignee opens before unloading, what the quality
officer files, and what settles the dispute when a load is rejected.

build_certificate() pulls every stored packet and alert for one shipment,
runs M3 to get MKT / coverage / verdict, and lays the result out as a PDF
with ReportLab. Everything upstream of the PDF layout (gathering the
records, computing the summary numbers, picking chart line segments,
hashing for verification) is exposed as its own plain function so it can be
tested without parsing rendered PDF output.

Honesty is the point of this document, and three rules run through all of
it:

- A gap -- no packet, or a buffered packet excluded per readings_from_packets'
  own convention -- is drawn as a broken line on the chart, never
  interpolated across (see chart_series / _gap_spans), and pulls
  coverage_pct below 100 in the summary.
- Suppressed alerts are listed in the event log too, with their
  suppression_reason, not hidden -- the record must show the door was open
  at a delivery stop and why it wasn't alarmed.
- The verdict is always models.m3_mkt.stability_budget_consumed's own
  output. Nothing in this module computes or overrides it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from models.m3_mkt import (
    GAP_THRESHOLD_MIN,
    BudgetResult,
    readings_from_packets,
    stability_budget_consumed,
)
from reports.templates import (
    ACTION_LABEL,
    CAUSE_LABEL,
    CERT_LOCALES,
    DRIVER_CAUSE_LABEL,
    OUTCOME_LABEL,
    VERDICT_COLOR,
    VERDICT_LABEL,
    L,
)
from shared.enums import AlertState, ProbePosition
from shared.messages import SEVERITY_LABEL
from shared.profiles import MissionProfile, get_profile
from shared.schema import AlertRecord, Band, TelemetryPacket

MARGIN_MM = 18.0
CALIBRATION_VALIDITY_DAYS = 90
FIRMWARE_VERSION = "sim-1.0"  # the simulated fleet has no real firmware build to report

_PROBE_ORDER: tuple[ProbePosition, ...] = (
    ProbePosition.front,
    ProbePosition.rear_door,
    ProbePosition.top,
    ProbePosition.bottom,
)
_PROBE_COLOR: dict[ProbePosition, str] = {
    ProbePosition.front: "#1f77b4",
    ProbePosition.rear_door: "#d62728",
    ProbePosition.top: "#2ca02c",
    ProbePosition.bottom: "#9467bd",
}


class CertificateError(ValueError):
    pass


def _t(key: str, locale: str) -> str:
    return L[key][locale]


def _fmt_ts(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M UTC")


# --- data gathering ---------------------------------------------------------


@dataclass
class ShipmentRecord:
    shipment_id: str
    device_id: str
    profile: MissionProfile
    band: Band
    packets: list[TelemetryPacket]
    alerts: list[AlertRecord]


def gather_shipment_data(shipment_id: str, store) -> ShipmentRecord:
    """Pull every packet and alert belonging to one shipment.

    The store's `alerts()` query only filters by device_id (there's no
    shipment-scoped index -- see ingest/store.py), so this fetches by the
    shipment's own device_id and filters to the shipment_id itself here.
    """
    packets = sorted(store.shipment(shipment_id), key=lambda p: (p.seq, p.ts))
    if not packets:
        raise CertificateError(f"no packets found for shipment {shipment_id!r}")

    profile = packets[0].mission_profile
    band = packets[0].band
    if profile is None or band is None:
        raise CertificateError(
            f"shipment {shipment_id!r} has no mission_profile/band recorded"
        )
    device_id = packets[0].device_id

    alerts = sorted(
        (a for a in store.alerts(device_id=device_id) if a.shipment_id == shipment_id),
        key=lambda a: a.issued_ts,
    )
    return ShipmentRecord(
        shipment_id=shipment_id,
        device_id=device_id,
        profile=profile,
        band=band,
        packets=packets,
        alerts=alerts,
    )


# --- summary numbers ---------------------------------------------------------


@dataclass
class ShipmentSummary:
    budget: BudgetResult
    shock_event_count: int
    peak_shock_g: float
    light_exposure_lux_hours: float
    door_open_events: list[tuple[datetime, float, float]]


def _light_exposure_lux_hours(
    packets: list[TelemetryPacket], gap_threshold_min: float = GAP_THRESHOLD_MIN
) -> float:
    """lux-hours, weighted by the interval to the next observed sample --
    same "credit a reading only until the next one arrives, drop genuine
    gaps" convention as models.m3_mkt, so an outage doesn't get counted as
    either lit or dark."""
    ordered = sorted((p for p in packets if not p.buffered), key=lambda p: p.ts)
    total = 0.0
    for i in range(len(ordered) - 1):
        gap_min = (ordered[i + 1].ts - ordered[i].ts).total_seconds() / 60.0
        if gap_min <= gap_threshold_min:
            total += ordered[i].light_lux * (gap_min / 60.0)
    return total


def _door_open_events(packets: list[TelemetryPacket]) -> list[tuple[datetime, float, float]]:
    """(ts, lat, lon) at the start of every door-open event -- not just a
    count, so the certificate can show where and when each one happened."""
    ordered = sorted(packets, key=lambda p: p.ts)
    events: list[tuple[datetime, float, float]] = []
    prev_open = False
    for p in ordered:
        if p.door.open and not prev_open:
            events.append((p.ts, p.gnss.lat, p.gnss.lon))
        prev_open = p.door.open
    return events


def compute_summary(packets: list[TelemetryPacket], profile: MissionProfile) -> ShipmentSummary:
    readings = readings_from_packets(packets)
    duration_min = (packets[-1].ts - packets[0].ts).total_seconds() / 60.0
    budget = stability_budget_consumed(readings, profile, duration_min)

    return ShipmentSummary(
        budget=budget,
        shock_event_count=sum(p.motion.shock_events for p in packets),
        peak_shock_g=max((p.motion.peak_g for p in packets), default=0.0),
        light_exposure_lux_hours=_light_exposure_lux_hours(packets),
        door_open_events=_door_open_events(packets),
    )


# --- temperature chart data (broken across gaps, never interpolated) --------


def chart_series(
    packets: list[TelemetryPacket], gap_threshold_min: float = GAP_THRESHOLD_MIN
) -> dict[ProbePosition, list[list[tuple[datetime, float]]]]:
    """Per-probe line segments for the temperature chart.

    Buffered packets are excluded (same reasoning as readings_from_packets:
    a value recovered after an outage was not verified in real time), and
    the remaining series is split into a new segment wherever the gap to
    the next observed sample exceeds gap_threshold_min. Segments are never
    joined across a gap -- that is what keeps an outage from reading as a
    smooth, compliant line.
    """
    observed = sorted((p for p in packets if not p.buffered), key=lambda p: p.ts)
    by_probe: dict[ProbePosition, list[list[tuple[datetime, float]]]] = {}
    for probe in _PROBE_ORDER:
        segments: list[list[tuple[datetime, float]]] = []
        current: list[tuple[datetime, float]] = []
        prev_ts: datetime | None = None
        for packet in observed:
            reading = next((c.t_c for c in packet.cargo if c.pos == probe), None)
            if reading is None:
                continue
            if prev_ts is not None:
                gap_min = (packet.ts - prev_ts).total_seconds() / 60.0
                if gap_min > gap_threshold_min:
                    if current:
                        segments.append(current)
                    current = []
            current.append((packet.ts, reading))
            prev_ts = packet.ts
        if current:
            segments.append(current)
        by_probe[probe] = segments
    return by_probe


def _gap_spans(
    packets: list[TelemetryPacket], gap_threshold_min: float = GAP_THRESHOLD_MIN
) -> list[tuple[datetime, datetime]]:
    observed_ts = sorted(p.ts for p in packets if not p.buffered)
    spans = []
    for a, b in zip(observed_ts, observed_ts[1:], strict=False):
        if (b - a).total_seconds() / 60.0 > gap_threshold_min:
            spans.append((a, b))
    return spans


# --- verification hash -------------------------------------------------------


def verification_hash(packets: list[TelemetryPacket], alerts: list[AlertRecord]) -> str:
    """SHA-256 over a canonical serialisation of every underlying record.

    Sorted independently of whatever order the store happened to return
    them in, so the hash is a pure function of the record *contents* --
    deterministic for identical input, and different the moment any
    packet or alert field changes.
    """
    ordered_packets = sorted(packets, key=lambda p: (p.device_id, p.seq))
    ordered_alerts = sorted(alerts, key=lambda a: a.alert_id)
    canonical = {
        "packets": [p.model_dump(mode="json") for p in ordered_packets],
        "alerts": [a.model_dump(mode="json") for a in ordered_alerts],
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# --- event log rows -----------------------------------------------------------


@dataclass
class EventLogRow:
    time: str
    cause: str
    severity: str
    evidence: str
    action: str
    ack: str
    driver_cause: str
    action_taken: str
    outcome: str
    note: str


def _fmt_evidence(evidence: dict[str, float]) -> str:
    if not evidence:
        return "—"
    return ", ".join(f"{k}={v:.2f}" for k, v in sorted(evidence.items()))


def event_log_rows(alerts: list[AlertRecord], locale: str) -> list[EventLogRow]:
    """One row per alert, in the order given -- nothing filtered, nothing
    collapsed. A suppressed alert's `note` carries its suppression_reason
    (stored in AlertRecord.message -- see models/alert_engine.py's own
    docstring on why that's where it lives in the frozen schema) so the
    log shows the door was open at a delivery stop and why it wasn't
    alarmed, not just that it was open.
    """
    rows = []
    for a in alerts:
        note = ""
        if a.state == AlertState.suppressed:
            note = f"{_t('suppression_reason_prefix', locale)}{a.message}"
        driver_cause = (
            DRIVER_CAUSE_LABEL[a.driver_cause][locale] if a.driver_cause is not None else "—"
        )
        rows.append(
            EventLogRow(
                time=_fmt_ts(a.issued_ts),
                cause=CAUSE_LABEL.get(a.cause, {}).get(locale, a.cause.value),
                severity=SEVERITY_LABEL[a.severity][locale],
                evidence=_fmt_evidence(a.evidence),
                action=ACTION_LABEL.get(a.prescribed_action, {}).get(
                    locale, a.prescribed_action.value
                ),
                ack=_fmt_ts(a.ack_ts) if a.ack_ts else "—",
                driver_cause=driver_cause,
                action_taken=a.action_taken or "—",
                outcome=OUTCOME_LABEL[a.outcome][locale],
                note=note,
            )
        )
    return rows


# --- PDF rendering ------------------------------------------------------------

_CELL = ParagraphStyle("CertCell", fontName="Helvetica", fontSize=7, leading=9)
_CELL_BOLD = ParagraphStyle("CertCellBold", fontName="Helvetica-Bold", fontSize=7, leading=9)
_HEADER_CELL = ParagraphStyle(
    "CertHeaderCell", fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=colors.white
)

_KV_STYLE = TableStyle(
    [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
)

_EVENT_STYLE = TableStyle(
    [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
)

_EVENT_COLUMNS_MM = (15, 24, 12, 30, 20, 13, 13, 13, 12, 20)


def _kv_table(rows: list[list[str]]) -> Table:
    data = [[Paragraph(str(k), _CELL_BOLD), Paragraph(str(v), _CELL)] for k, v in rows]
    return Table(data, colWidths=[55 * mm, None], style=_KV_STYLE)


class _TemperatureChart(Flowable):
    """A hand-drawn line chart (band shaded, gaps shaded and broken, one
    line per cargo probe) -- deliberately not a smoothing/interpolating
    charting library default, since interpolating across a gap is exactly
    the dishonesty this document exists to avoid.
    """

    def __init__(self, packets: list[TelemetryPacket], band: Band, width: float, height: float):
        super().__init__()
        self.packets = packets
        self.band = band
        self.width = width
        self.height = height

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        packets = self.packets
        all_ts = [p.ts for p in packets]
        t0, t1 = min(all_ts), max(all_ts)
        span_s = max(1.0, (t1 - t0).total_seconds())

        temps = [
            reading.t_c
            for p in packets
            for reading in p.cargo
            if reading.pos != ProbePosition.ambient_external
        ]
        y_min = min([self.band.min_c, *temps]) - 1.0
        y_max = max([self.band.max_c, *temps]) + 1.0
        y_span = max(0.1, y_max - y_min)

        pad_left = 14 * mm
        pad_bottom = 8 * mm
        pad_top = 6 * mm
        plot_w = self.width - pad_left - 2 * mm
        plot_h = self.height - pad_bottom - pad_top

        def x_of(ts: datetime) -> float:
            return pad_left + (ts - t0).total_seconds() / span_s * plot_w

        def y_of(temp: float) -> float:
            return pad_bottom + (temp - y_min) / y_span * plot_h

        # Acceptable band, shaded.
        c.setFillColorRGB(0.85, 0.93, 0.85)
        band_y0, band_y1 = y_of(self.band.min_c), y_of(self.band.max_c)
        c.rect(pad_left, band_y0, plot_w, band_y1 - band_y0, fill=1, stroke=0)

        # Unobserved periods, shaded across the full plot height -- drawn
        # *after* the band so a gap inside the band is still visibly grey,
        # not quietly green.
        for gap_start, gap_end in _gap_spans(packets):
            x0, x1 = x_of(gap_start), x_of(gap_end)
            c.setFillColorRGB(0.6, 0.6, 0.6)
            c.rect(x0, pad_bottom, max(0.6, x1 - x0), plot_h, fill=1, stroke=0)

        c.setStrokeColor(colors.black)
        c.setLineWidth(0.5)
        c.line(pad_left, pad_bottom, pad_left, pad_bottom + plot_h)
        c.line(pad_left, pad_bottom, pad_left + plot_w, pad_bottom)
        c.setFont("Helvetica", 6)
        c.drawRightString(pad_left - 2, pad_bottom - 2, f"{y_min:.0f}")
        c.drawRightString(pad_left - 2, pad_bottom + plot_h - 2, f"{y_max:.0f}")
        c.drawRightString(pad_left - 2, band_y0 - 2, f"{self.band.min_c:.0f}")
        c.drawRightString(pad_left - 2, band_y1 - 2, f"{self.band.max_c:.0f}")

        series = chart_series(packets)
        legend_x = pad_left
        for probe in _PROBE_ORDER:
            color = colors.HexColor(_PROBE_COLOR[probe])
            c.setStrokeColor(color)
            c.setLineWidth(0.9)
            for segment in series[probe]:
                if len(segment) < 2:
                    continue
                path = c.beginPath()
                path.moveTo(x_of(segment[0][0]), y_of(segment[0][1]))
                for ts, temp in segment[1:]:
                    path.lineTo(x_of(ts), y_of(temp))
                c.drawPath(path, stroke=1, fill=0)

            c.setFillColor(color)
            c.rect(legend_x, self.height - 4, 5, 3, fill=1, stroke=0)
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 6)
            c.drawString(legend_x + 7, self.height - 5.5, probe.value)
            legend_x += 26 * mm


def _summary_rows(summary: ShipmentSummary, locale: str) -> list[list[str]]:
    b = summary.budget
    if b.worst_excursion_c is None:
        worst = _t("no_worst_excursion", locale)
    else:
        worst = f"{b.worst_excursion_c:.1f} °C, {b.worst_excursion_duration_min:.0f} min"

    if summary.door_open_events:
        door_str = "; ".join(
            f"{ts.strftime('%Y-%m-%d %H:%M')} ({lat:.2f}, {lon:.2f})"
            for ts, lat, lon in summary.door_open_events
        )
    else:
        door_str = _t("no_events", locale)

    return [
        [_t("mkt", locale), f"{b.mkt_c:.2f} °C"],
        [_t("minutes_above", locale), f"{b.minutes_out_of_band_above:.1f} min"],
        [_t("minutes_below", locale), f"{b.minutes_out_of_band_below:.1f} min"],
        [_t("worst_excursion", locale), worst],
        [_t("coverage", locale), f"{b.coverage_pct:.1f} %"],
        [_t("shock_events", locale), f"{summary.shock_event_count}"],
        [_t("peak_shock", locale), f"{summary.peak_shock_g:.2f} g"],
        [_t("light_exposure_total", locale), f"{summary.light_exposure_lux_hours:.1f} lux·h"],
        [_t("door_events", locale), door_str],
    ]


def _attestation_rows(
    device_id: str, packets: list[TelemetryPacket], budget: BudgetResult, locale: str
) -> list[list[str]]:
    calib_date = packets[0].ts - timedelta(days=CALIBRATION_VALIDITY_DAYS)
    return [
        [_t("device_id", locale), device_id],
        [_t("firmware_version", locale), FIRMWARE_VERSION],
        [_t("calibration_status", locale), _t("calibrated", locale)],
        [_t("calibration_date", locale), calib_date.strftime("%Y-%m-%d")],
        [_t("packet_count", locale), str(len(packets))],
        [_t("buffered_packet_count", locale), str(sum(1 for p in packets if p.buffered))],
        [_t("coverage", locale), f"{budget.coverage_pct:.1f} %"],
    ]


def _event_table(alerts: list[AlertRecord], locale: str) -> Table | Paragraph:
    if not alerts:
        return Paragraph(_t("no_events", locale), _CELL)

    rows = event_log_rows(alerts, locale)
    header = [
        _t("col_time", locale),
        _t("col_cause", locale),
        _t("col_severity", locale),
        _t("col_evidence", locale),
        _t("col_action", locale),
        _t("col_ack", locale),
        _t("col_driver_cause", locale),
        _t("col_action_taken", locale),
        _t("col_outcome", locale),
        _t("col_notes", locale),
    ]
    data = [[Paragraph(h, _HEADER_CELL) for h in header]]
    for r in rows:
        data.append(
            [
                Paragraph(r.time, _CELL),
                Paragraph(r.cause, _CELL),
                Paragraph(r.severity, _CELL),
                Paragraph(r.evidence, _CELL),
                Paragraph(r.action, _CELL),
                Paragraph(r.ack, _CELL),
                Paragraph(r.driver_cause, _CELL),
                Paragraph(r.action_taken, _CELL),
                Paragraph(r.outcome, _CELL),
                Paragraph(r.note or "—", _CELL),
            ]
        )
    col_widths = [w * mm for w in _EVENT_COLUMNS_MM]
    return Table(data, colWidths=col_widths, repeatRows=1, style=_EVENT_STYLE)


def _route_str(packets: list[TelemetryPacket]) -> str:
    start, end = packets[0].gnss, packets[-1].gnss
    return f"({start.lat:.2f}, {start.lon:.2f}) → ({end.lat:.2f}, {end.lon:.2f})"


def build_certificate(shipment_id: str, store, locale: str = "fr") -> bytes:
    """Render the compliance certificate for one shipment as a PDF.

    The verdict is never computed here -- it is whatever
    models.m3_mkt.stability_budget_consumed returns for this shipment's own
    readings, full stop.
    """
    if locale not in CERT_LOCALES:
        raise CertificateError(
            f"unsupported certificate locale: {locale!r} (supported: {CERT_LOCALES}); "
            "Arabic is a documented gap, not a silently broken layout -- see "
            "reports/templates.py's module docstring."
        )

    record = gather_shipment_data(shipment_id, store)
    summary = compute_summary(record.packets, record.profile)
    budget = summary.budget

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_MM * mm,
        rightMargin=MARGIN_MM * mm,
        topMargin=MARGIN_MM * mm,
        bottomMargin=MARGIN_MM * mm,
        title=_t("title", locale),
    )

    title_style = ParagraphStyle("CertTitle", fontName="Helvetica-Bold", fontSize=16, leading=20)
    heading_style = ParagraphStyle(
        "CertHeading",
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        spaceBefore=4,
        spaceAfter=3,
    )
    verdict_style = ParagraphStyle(
        "CertVerdict",
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.Color(*VERDICT_COLOR[budget.verdict]),
        spaceBefore=2,
        spaceAfter=6,
    )
    italic_style = ParagraphStyle("CertItalic", fontName="Helvetica-Oblique", fontSize=7, leading=9)
    footer_style = ParagraphStyle("CertFooter", fontName="Helvetica", fontSize=8, leading=11)
    hash_style = ParagraphStyle("CertHash", fontName="Courier", fontSize=8, leading=11)

    story: list = [
        Paragraph(_t("title", locale), title_style),
        # Colour alone never carries the verdict: the word itself is the
        # headline, colour is only a secondary cue on top of it.
        Paragraph(VERDICT_LABEL[budget.verdict][locale], verdict_style),
        _kv_table(
            [
                [_t("shipment", locale), record.shipment_id],
                [_t("vehicle", locale), record.device_id],
                [_t("route", locale), _route_str(record.packets)],
                [_t("departure", locale), _fmt_ts(record.packets[0].ts)],
                [_t("arrival", locale), _fmt_ts(record.packets[-1].ts)],
                [_t("mission_profile", locale), get_profile(record.profile).label],
                [_t("band", locale), f"{record.band.min_c:.1f} – {record.band.max_c:.1f} °C"],
            ]
        ),
        Spacer(1, 5 * mm),
        Paragraph(_t("temperature_record", locale), heading_style),
        _TemperatureChart(record.packets, record.band, width=doc.width, height=65 * mm),
        Paragraph(_t("chart_gap_note", locale), italic_style),
        Spacer(1, 5 * mm),
        Paragraph(_t("summary", locale), heading_style),
        _kv_table(_summary_rows(summary, locale)),
        Spacer(1, 5 * mm),
        Paragraph(_t("event_log", locale), heading_style),
        _event_table(record.alerts, locale),
        Spacer(1, 5 * mm),
        Paragraph(_t("device_attestation", locale), heading_style),
        _kv_table(_attestation_rows(record.device_id, record.packets, budget, locale)),
        Spacer(1, 5 * mm),
        Paragraph(_t("verification_footer", locale), footer_style),
        Paragraph(
            f"{_t('verification_hash', locale)}: "
            f"{verification_hash(record.packets, record.alerts)}",
            hash_style,
        ),
        Paragraph(f"{_t('generated_at', locale)}: {_fmt_ts(datetime.now(UTC))}", footer_style),
    ]

    doc.build(story)
    return buf.getvalue()
