from __future__ import annotations

from models.electrical_health import ElectricalHealthMonitor
from shared.enums import FaultCause
from simulator.electrical import ElectricalSim
from simulator.scenarios import NominalScenario, RefrigerantLossScenario


def test_zero_anomalies_on_nominal() -> None:
    scenario = NominalScenario()
    monitor = ElectricalHealthMonitor(dt_min=1.0)
    elec = ElectricalSim(scenario.profile)

    anomalies = []
    for packet in scenario.run(dt_s=60.0):
        expected = elec.expected_duty_pct(packet.ambient_c, packet.gnss.speed_kmh)
        result = monitor.update(packet, expected)
        if result.cause is not None:
            anomalies.append((packet.seq, result.cause))

    assert anomalies == []


def test_refrigerant_loss_detected_before_thermal_breach() -> None:
    scenario = RefrigerantLossScenario()
    # The scenario's own default_duration_min (48h) never actually breaches
    # band at the 0.3 capacity floor; run long enough that it does, so
    # "detected before breach" is a real assertion, not a vacuous one.
    duration_min = 6000.0
    gt = scenario.ground_truth(duration_min=duration_min)
    breach_t = gt["expected_thermal_breach_min"]
    assert breach_t is not None, "expected a real breach at this duration"

    monitor = ElectricalHealthMonitor(dt_min=1.0)
    elec = ElectricalSim(scenario.profile)

    detect_t: float | None = None
    t_min = 0.0
    for packet in scenario.run(duration_min=duration_min, dt_s=60.0):
        expected = elec.expected_duty_pct(packet.ambient_c, packet.gnss.speed_kmh)
        result = monitor.update(packet, expected)
        if detect_t is None:
            if result.cause == FaultCause.refrigerant_loss:
                detect_t = t_min
            elif result.cause is not None:
                raise AssertionError(f"unexpected cause before refrigerant_loss: {result.cause}")
        t_min += 1.0

    assert detect_t is not None
    if breach_t is not None:
        assert detect_t < breach_t
