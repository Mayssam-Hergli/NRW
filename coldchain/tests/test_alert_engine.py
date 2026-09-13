from __future__ import annotations

from datetime import UTC, datetime, timedelta

from models.alert_engine import AlertEngine, _render_message
from models.fusion import Diagnosis
from shared.enums import AlertState, DriverCause, FaultCause, Outcome, Severity
from tests.test_fusion import _packet

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _diag(
    cause=FaultCause.unit_off,
    severity=Severity.critical,
    evidence=None,
    suppressed=False,
    suppression_reason=None,
    action=None,
) -> Diagnosis:
    return Diagnosis(
        cause=cause,
        severity=severity,
        evidence=evidence or {},
        prescribed_action=action,
        suppressed=suppressed,
        suppression_reason=suppression_reason,
        confidence=0.9,
    )


def test_unacknowledged_critical_escalates_after_five_minutes() -> None:
    engine = AlertEngine(escalate_after_min=5.0)
    p0 = _packet(t_c=7.8, seq=0, ts=T0)
    (record,) = engine.update(p0, _diag())
    assert record.state == AlertState.critical

    p1 = _packet(t_c=7.8, seq=4, ts=T0 + timedelta(minutes=4))
    result = engine.update(p1, _diag())
    assert result == [] or all(r.state != AlertState.escalated for r in result)

    p2 = _packet(t_c=7.8, seq=5, ts=T0 + timedelta(minutes=5))
    (escalated,) = engine.update(p2, _diag())
    assert escalated.state == AlertState.escalated
    assert escalated.tier == 3
    assert escalated.alert_id == record.alert_id


def test_acknowledging_moves_to_acknowledged_and_records_driver_cause() -> None:
    engine = AlertEngine()
    p0 = _packet(t_c=7.8, seq=0, ts=T0)
    (record,) = engine.update(p0, _diag())

    acked = engine.acknowledge(
        record.alert_id, T0 + timedelta(minutes=1), driver_cause=DriverCause.unit_failure
    )
    assert acked.state == AlertState.acknowledged
    assert acked.ack_ts == T0 + timedelta(minutes=1)
    assert acked.driver_cause == DriverCause.unit_failure


def test_recovery_after_ack_resolves_no_recovery_returns_to_critical() -> None:
    # Recovery path.
    engine = AlertEngine()
    p0 = _packet(t_c=7.8, seq=0, ts=T0)
    (record,) = engine.update(p0, _diag())
    engine.acknowledge(record.alert_id, T0 + timedelta(minutes=1))

    p1 = _packet(t_c=5.0, seq=2, ts=T0 + timedelta(minutes=2))
    (resolved,) = engine.update(p1, _diag(cause=None, severity=None))
    assert resolved.state == AlertState.resolved
    assert resolved.outcome == Outcome.recovered
    assert resolved.resolved_ts == T0 + timedelta(minutes=2)

    # No-recovery path: same cause still active after ack -> critical again.
    engine2 = AlertEngine()
    p2 = _packet(t_c=7.8, seq=0, ts=T0)
    (record2,) = engine2.update(p2, _diag())
    engine2.acknowledge(record2.alert_id, T0 + timedelta(minutes=1))

    p3 = _packet(t_c=8.2, seq=2, ts=T0 + timedelta(minutes=2))
    (still_broken,) = engine2.update(p3, _diag())
    assert still_broken.state == AlertState.critical
    assert still_broken.outcome == Outcome.not_recovered
    assert still_broken.alert_id == record2.alert_id


def test_worsening_condition_updates_existing_alert_not_a_second_one() -> None:
    engine = AlertEngine()
    p0 = _packet(t_c=6.5, seq=0, ts=T0)
    (first,) = engine.update(p0, _diag(severity=Severity.watch, cause=FaultCause.seal_failure))
    assert first.state == AlertState.watch

    p1 = _packet(t_c=7.2, seq=1, ts=T0 + timedelta(minutes=1))
    (second,) = engine.update(p1, _diag(severity=Severity.warning, cause=FaultCause.seal_failure))
    assert second.alert_id == first.alert_id
    assert second.state == AlertState.warning
    assert len(engine.active_alerts()) == 1


def test_door_suppressed_then_warning_is_one_alert_not_two() -> None:
    # The door-family grouping (offload_stop -> door_unsecured) means the
    # state diagram's "suppressed -> warning" arrow is one alert
    # transitioning, matching test_fusion.py's own headline scenario.
    engine = AlertEngine()
    p0 = _packet(t_c=6.0, door_open=True, door_events=1, seq=0, ts=T0)
    (suppressed,) = engine.update(
        p0,
        _diag(
            cause=FaultCause.offload_stop,
            severity=None,
            suppressed=True,
            suppression_reason="door open 2 min, within the 10-min offload dwell limit",
        ),
    )
    assert suppressed.state == AlertState.suppressed
    # AlertRecord (frozen) has no suppression_reason field -- it's carried
    # in message instead (see models/alert_engine.py::_message_for).
    assert suppressed.message == "door open 2 min, within the 10-min offload dwell limit"

    p1 = _packet(t_c=7.0, door_open=True, door_events=1, seq=12, ts=T0 + timedelta(minutes=12))
    (escalated,) = engine.update(
        p1, _diag(cause=FaultCause.door_unsecured, severity=Severity.warning)
    )
    assert escalated.alert_id == suppressed.alert_id
    assert escalated.state == AlertState.warning
    assert len(engine.active_alerts()) == 1


def test_alert_record_message_is_produced_by_rendering_cause_and_evidence() -> None:
    engine = AlertEngine()
    evidence = {"dev_pp": 24.0}
    p0 = _packet(t_c=6.5, seq=0, ts=T0)
    (record,) = engine.update(
        p0,
        _diag(cause=FaultCause.refrigerant_loss, severity=Severity.warning, evidence=evidence),
    )

    # The stored message must be exactly what re-rendering cause+evidence
    # produces -- never an independently hand-composed sentence. This is
    # the module's own documented rendering function (render(), with its
    # documented fallback for the no-countdown case), applied to the
    # record's own stored fields.
    expected = _render_message(record.cause, record.severity, record.evidence, "fr")
    assert record.message == expected
    assert record.cause == FaultCause.refrigerant_loss
    assert record.evidence == evidence


def test_alert_record_message_has_no_countdown_when_none_was_available() -> None:
    # refrigerant_loss's predictive window carries no predicted_breach_min
    # by design (see test_fusion.py) -- the stored message must not invent
    # one via shared.messages.render()'s countdown clause.
    engine = AlertEngine()
    p0 = _packet(t_c=6.5, seq=0, ts=T0)
    (record,) = engine.update(
        p0, _diag(cause=FaultCause.refrigerant_loss, severity=Severity.warning, evidence={})
    )
    assert record.predicted_breach_min is None
    assert "None" not in record.message
