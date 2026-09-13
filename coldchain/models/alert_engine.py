"""Alert engine -- the AlertRecord lifecycle state machine.

Where models/fusion.py answers "what's wrong right now" (a stateless
Diagnosis per packet), this module answers "what should the persisted
AlertRecord for that look like, and has anything about its lifecycle
changed" -- state machine:

    nominal -> suppressed -> nominal | warning
    nominal -> watch -> nominal | warning
    warning -> nominal (forecast clears) | critical | acknowledged
    nominal -> critical (hard fault)
    critical -> acknowledged | escalated
    escalated -> acknowledged
    acknowledged -> resolved | critical (no recovery)
    resolved -> nominal | end

Deduplication is "one ongoing alert per cause per vehicle" -- with one
documented exception. offload_stop and door_unsecured are two different
FaultCause values but the *same* physical event evolving (a door that's
been open too long doesn't stop being the door event just because its
label changes) -- the state diagram's own "suppressed -> warning" arrow
only makes sense as one alert transitioning, not one being closed and a
second opened. _ALERT_GROUP maps both to a shared tracking key ("door");
every other cause is its own group, one-to-one.

Known limitation, inherited from fuse()'s API (not touched for this task):
fuse() returns one Diagnosis per packet -- the single dominant concern, not
every concurrently-true one. If two unrelated causes were genuinely active
at once (e.g. a predictive refrigerant_loss warning *and* a separate door
event), a packet reporting the door would not carry any signal about
refrigerant_loss that packet. This engine only ever acts on the group its
diagnosis belongs to per call (plus a device-wide clear when diagnosis.cause
is None, which fuse() only returns when nothing at all is wrong) -- it does
not silently resolve a tracked alert just because a different concern took
priority this packet.

message is always rendered via shared.messages.render() from the record's
own cause/evidence at write time (audience="driver", locale="fr" -- the
project default), never hand-composed. This is a convenience snapshot for
anything reading the raw record, not the display source of truth: every UI
that shows it should re-render per the *reader's* locale from cause and
evidence, exactly as the dashboard already does.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timedelta

from models.fusion import Diagnosis
from shared.enums import AlertState, DriverCause, FaultCause, Outcome, PrescribedAction, Severity
from shared.messages import CAUSE_COPY, render
from shared.schema import AlertRecord, TelemetryPacket

ESCALATE_AFTER_MIN_DEFAULT = 5.0

# offload_stop and door_unsecured are the same evolving door event -- see
# module docstring. Every other cause is its own one-member group.
_ALERT_GROUP: dict[FaultCause, str] = {
    FaultCause.offload_stop: "door",
    FaultCause.door_unsecured: "door",
}


def _group_for(cause: FaultCause) -> str:
    return _ALERT_GROUP.get(cause, cause.value)


_SEVERITY_TO_STATE: dict[Severity, AlertState] = {
    Severity.watch: AlertState.watch,
    Severity.warning: AlertState.warning,
    Severity.critical: AlertState.critical,
}

_FALLBACK_ACTION = PrescribedAction.call_dispatch


@dataclass
class _Tracked:
    record: AlertRecord
    group: str
    critical_since: datetime | None = None
    tier: int = 1


def _message_for(diagnosis: Diagnosis, severity_for_render: Severity, locale: str) -> str:
    """AlertRecord (frozen) has no suppression_reason field -- only
    Diagnosis does. "Suppression is not silence: a suppressed event is
    still recorded with its suppression_reason" has nowhere else to live
    in the frozen schema, so a suppressed record's message *is* the
    suppression reason (there's no cause-driven "why this is fine for now"
    copy to render anyway) rather than the usual rendered instruction.
    """
    if diagnosis.suppressed:
        return diagnosis.suppression_reason or "suppressed"
    assert diagnosis.cause is not None
    return _render_message(diagnosis.cause, severity_for_render, diagnosis.evidence, locale)


def _render_message(
    cause: FaultCause, severity: Severity, evidence: dict[str, float], locale: str
) -> str:
    breach_min = evidence.get("predicted_breach_min")
    if breach_min is not None:
        # render()'s signature is (..., evidence=None, **ctx) -- placeholder
        # values go in as direct keyword arguments, not a `ctx={...}` dict
        # (that would land as a single key literally named "ctx" instead of
        # unpacking eta_min, which is exactly the bug this comment is here
        # to stop someone reintroducing).
        return render(
            cause=cause,
            severity=severity,
            audience="driver",
            locale=locale,
            evidence=evidence,
            eta_min=breach_min,
        )
    if severity == Severity.watch:
        # SAFE_NOW_CLAUSE carries no placeholder -- render() works as-is.
        return render(
            cause=cause, severity=severity, audience="driver", locale=locale, evidence=evidence
        )
    # No real countdown available even though severity is certain --
    # e.g. unit_off is critical regardless of what M1 has to say, and
    # refrigerant_loss's predictive-window warning is deliberately
    # time-free (fusion must not wait on M1 there). render()'s driver
    # audience always appends a countdown clause for non-watch severities,
    # which needs a number we don't honestly have. shared/ is frozen, so
    # rather than inventing an eta_min, fall back to the bare instruction
    # line via the same public CAUSE_COPY table render() itself reads --
    # still clear and actionable, just without a specific ETA it would be
    # wrong to fabricate.
    return CAUSE_COPY[cause]["driver"][locale]


class AlertEngine:
    """One instance covers a whole fleet: active alerts are keyed by
    (device_id, group), so state for different vehicles never mixes."""

    def __init__(self, escalate_after_min: float = ESCALATE_AFTER_MIN_DEFAULT) -> None:
        self.escalate_after_min = escalate_after_min
        self._active: dict[tuple[str, str], _Tracked] = {}
        self._id_counter = itertools.count(1)

    def _new_alert_id(self, device_id: str, group: str) -> str:
        return f"{device_id}-{group}-{next(self._id_counter)}"

    def active_alerts(self, device_id: str | None = None) -> list[AlertRecord]:
        return [
            t.record
            for (dev, _group), t in self._active.items()
            if device_id is None or dev == device_id
        ]

    # -- escalation timing -------------------------------------------------

    def _tick_escalations(self, device_id: str, now: datetime) -> list[AlertRecord]:
        """Advances any of this device's tracked alerts from critical to
        escalated once unacknowledged for escalate_after_min, independent
        of whatever the current packet's own diagnosis is about."""
        changed = []
        threshold = timedelta(minutes=self.escalate_after_min)
        for (dev, _group), tracked in self._active.items():
            if dev != device_id:
                continue
            record = tracked.record
            if (
                record.state == AlertState.critical
                and record.ack_ts is None
                and tracked.critical_since is not None
                and (now - tracked.critical_since) >= threshold
            ):
                tracked.tier = max(tracked.tier, 3)
                tracked.record = record.model_copy(
                    update={
                        "state": AlertState.escalated,
                        "tier": tracked.tier,
                        "escalated_ts": now,
                    }
                )
                changed.append(tracked.record)
        return changed

    # -- main entry point ----------------------------------------------------

    def update(
        self, packet: TelemetryPacket, diagnosis: Diagnosis, locale: str = "fr"
    ) -> list[AlertRecord]:
        """Feed one fresh Diagnosis for one packet. Returns every AlertRecord
        that changed this call -- normally one (the group the diagnosis is
        about), sometimes more (a timed-out escalation on a different,
        untouched alert happening to fall on the same packet)."""
        changed = self._tick_escalations(packet.device_id, packet.ts)

        if diagnosis.cause is None:
            # Confirmed healthy -- fuse() only returns this when nothing at
            # all is wrong, so every tracked alert for this device is
            # eligible to clear (see module docstring on why this is safe
            # only in the cause-is-None case, not otherwise).
            for key in [k for k in self._active if k[0] == packet.device_id]:
                result = self._clear_or_resolve(key, packet.ts)
                if result is not None:
                    changed.append(result)
        else:
            group = _group_for(diagnosis.cause)
            key = (packet.device_id, group)
            tracked = self._active.get(key)

            if tracked is None:
                changed.append(self._create(packet, diagnosis, group, locale))
            else:
                result = self._advance(tracked, packet, diagnosis, locale)
                if result is not None:
                    changed.append(result)

        # An alert the escalation tick already touched this call can also
        # get a second, redundant "refresh" update from _advance() just
        # below it -- keep the final version of each alert_id, not both.
        deduped: dict[str, AlertRecord] = {}
        for record in changed:
            deduped[record.alert_id] = record
        return list(deduped.values())

    def _create(
        self, packet: TelemetryPacket, diagnosis: Diagnosis, group: str, locale: str
    ) -> AlertRecord:
        if diagnosis.suppressed:
            state = AlertState.suppressed
            severity_for_render = Severity.watch
            tier = 1
        else:
            assert diagnosis.severity is not None
            state = _SEVERITY_TO_STATE[diagnosis.severity]
            severity_for_render = diagnosis.severity
            tier = 2 if diagnosis.severity == Severity.critical else 1

        assert diagnosis.cause is not None
        record = AlertRecord(
            alert_id=self._new_alert_id(packet.device_id, group),
            device_id=packet.device_id,
            shipment_id=packet.shipment_id,
            issued_ts=packet.ts,
            tier=tier,
            state=state,
            severity=diagnosis.severity if diagnosis.severity is not None else Severity.watch,
            cause=diagnosis.cause,
            evidence=diagnosis.evidence,
            predicted_breach_min=diagnosis.evidence.get("predicted_breach_min"),
            prescribed_action=diagnosis.prescribed_action or _FALLBACK_ACTION,
            message=_message_for(diagnosis, severity_for_render, locale),
            delivered_offline=packet.buffered,
        )
        tracked = _Tracked(
            record=record,
            group=group,
            critical_since=packet.ts if state == AlertState.critical else None,
            tier=tier,
        )
        self._active[(packet.device_id, group)] = tracked
        return record

    def _advance(
        self, tracked: _Tracked, packet: TelemetryPacket, diagnosis: Diagnosis, locale: str
    ) -> AlertRecord | None:
        record = tracked.record

        if record.state == AlertState.acknowledged:
            # "no recovery": the same group is still active -> back to
            # critical; anything else (including a lower severity for the
            # same cause -- an ack doesn't get reopened as a lesser
            # concern) counts as recovered once acknowledged.
            still_active = (
                diagnosis.cause is not None and _group_for(diagnosis.cause) == tracked.group
            )
            if still_active:
                tracked.critical_since = packet.ts
                tracked.tier = max(tracked.tier, 2)
                new_severity = Severity.critical
                updated = record.model_copy(
                    update={
                        "state": AlertState.critical,
                        "severity": new_severity,
                        "tier": tracked.tier,
                        "outcome": Outcome.not_recovered,
                        "evidence": diagnosis.evidence,
                        "predicted_breach_min": diagnosis.evidence.get("predicted_breach_min"),
                        "message": _render_message(
                            record.cause, new_severity, diagnosis.evidence, locale
                        ),
                    }
                )
            else:
                updated = record.model_copy(
                    update={
                        "state": AlertState.resolved,
                        "outcome": Outcome.recovered,
                        "resolved_ts": packet.ts,
                    }
                )
                del self._active[(packet.device_id, tracked.group)]
            tracked.record = updated
            return updated

        if record.state in (AlertState.critical, AlertState.escalated):
            # Ack is a separate, explicit action (see acknowledge()); short
            # of that, a still-active diagnosis just refreshes evidence.
            # Escalation timeout is handled by _tick_escalations, already
            # run before this method is reached.
            updated = record.model_copy(
                update={
                    "evidence": diagnosis.evidence,
                    "predicted_breach_min": diagnosis.evidence.get("predicted_breach_min"),
                }
            )
            tracked.record = updated
            return updated

        # suppressed / watch / warning: free to move in either direction,
        # including clearing back to nominal (removed from tracking) or
        # escalating straight past watch/warning into critical.
        if diagnosis.suppressed:
            new_state = AlertState.suppressed
            severity_for_render = Severity.watch
            new_severity = record.severity
        else:
            assert diagnosis.severity is not None
            new_state = _SEVERITY_TO_STATE[diagnosis.severity]
            severity_for_render = diagnosis.severity
            new_severity = diagnosis.severity

        if new_state == AlertState.critical and tracked.critical_since is None:
            tracked.critical_since = packet.ts
        elif new_state != AlertState.critical:
            tracked.critical_since = None
        if new_state == AlertState.critical:
            tracked.tier = max(tracked.tier, 2)

        updated = record.model_copy(
            update={
                "state": new_state,
                "severity": new_severity,
                "tier": tracked.tier,
                "cause": diagnosis.cause,
                "evidence": diagnosis.evidence,
                "predicted_breach_min": diagnosis.evidence.get("predicted_breach_min"),
                "prescribed_action": diagnosis.prescribed_action or record.prescribed_action,
                "message": _message_for(diagnosis, severity_for_render, locale),
            }
        )
        tracked.record = updated
        return updated

    def _clear_or_resolve(self, key: tuple[str, str], now: datetime) -> AlertRecord | None:
        tracked = self._active[key]
        record = tracked.record
        if record.state == AlertState.acknowledged:
            updated = record.model_copy(
                update={
                    "state": AlertState.resolved,
                    "outcome": Outcome.recovered,
                    "resolved_ts": now,
                }
            )
            del self._active[key]
            return updated
        if record.state in (AlertState.critical, AlertState.escalated):
            # Cannot clear without acknowledgment first -- stays as-is.
            return None
        # suppressed / watch / warning clear straight to nominal, i.e. just
        # stop tracking it; nothing to persist for "nominal" itself.
        del self._active[key]
        return None

    # -- driver/dispatcher action --------------------------------------------

    def acknowledge(
        self,
        alert_id: str,
        ts: datetime,
        driver_cause: DriverCause | None = None,
        action_taken: str | None = None,
    ) -> AlertRecord:
        for key, tracked in self._active.items():
            if tracked.record.alert_id == alert_id:
                ackable = (AlertState.warning, AlertState.critical, AlertState.escalated)
                if tracked.record.state not in ackable:
                    raise ValueError(
                        f"cannot acknowledge alert in state {tracked.record.state!r}"
                    )
                updated = tracked.record.model_copy(
                    update={
                        "state": AlertState.acknowledged,
                        "ack_ts": ts,
                        "driver_cause": driver_cause,
                        "action_taken": action_taken,
                    }
                )
                tracked.record = updated
                self._active[key] = tracked
                return updated
        raise KeyError(f"no active alert with id {alert_id!r}")
