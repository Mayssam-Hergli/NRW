"""Not a correctness test -- the acceptance report itself: fusion + the
alert engine run across all six stored scenarios, printing alerts emitted,
causes, severities, and suppressed-event count per scenario. Run with
`pytest tests/test_alert_engine_report.py -s` to see the table; nominal
showing zero alerts is asserted, not just printed, since that's the one
number this whole layer is not allowed to get wrong.
"""

from __future__ import annotations

from collections import Counter, deque

from shared.enums import AlertState
from simulator.electrical import ElectricalSim
from simulator.scenarios import SCENARIOS

from models.alert_engine import AlertEngine
from models.electrical_health import ElectricalHealthMonitor
from models.fusion import fuse
from models.m1_thermal import M1ThermalForecast

HISTORY_LIMIT = 30
_LONG_DURATION: dict[str, float] = {
    "refrigerant_loss": 6000.0,
    "compressor_failure": 260.0,
}


def _run_one_scenario(name: str, cls) -> dict:
    scenario = cls()
    duration = _LONG_DURATION.get(name)

    m1 = M1ThermalForecast()
    m2 = ElectricalHealthMonitor(dt_min=1.0)
    elec = ElectricalSim(scenario.profile)
    engine = AlertEngine()
    history: deque = deque(maxlen=HISTORY_LIMIT)

    causes: Counter[str] = Counter()
    severities: Counter[str] = Counter()
    suppressed_count = 0
    alerts_emitted = 0
    seen_alert_ids: set[str] = set()

    for packet in scenario.run(duration_min=duration, dt_s=60.0):
        r1 = m1.update(packet)
        expected_duty = elec.expected_duty_pct(packet.ambient_c, packet.gnss.speed_kmh)
        r2 = m2.update(packet, expected_duty)
        diagnosis = fuse(packet, r1, r2, None, list(history))
        changed = engine.update(packet, diagnosis)

        for record in changed:
            if record.alert_id not in seen_alert_ids:
                seen_alert_ids.add(record.alert_id)
                alerts_emitted += 1
            causes[record.cause.value] += 1
            severities[record.severity.value] += 1
            if record.state == AlertState.suppressed:
                suppressed_count += 1

        history.append(packet)

    return {
        "alerts_emitted": alerts_emitted,
        "causes": causes,
        "severities": severities,
        "suppressed_count": suppressed_count,
    }


def test_nominal_shows_zero_alerts() -> None:
    result = _run_one_scenario("nominal", SCENARIOS["nominal"])
    assert result["alerts_emitted"] == 0


def test_report_fusion_and_alert_engine_across_all_six_scenarios() -> None:
    print()
    print(f"{'scenario':<20} {'alerts':>7} {'suppressed':>11}  causes / severities")
    print("-" * 90)
    for name, cls in SCENARIOS.items():
        result = _run_one_scenario(name, cls)
        causes_str = ", ".join(f"{c}={n}" for c, n in result["causes"].most_common())
        severities_str = ", ".join(f"{s}={n}" for s, n in result["severities"].most_common())
        print(
            f"{name:<20} {result['alerts_emitted']:>7} {result['suppressed_count']:>11}  "
            f"{causes_str or '(none)'} | {severities_str or '(none)'}"
        )
        if name == "nominal":
            assert result["alerts_emitted"] == 0
