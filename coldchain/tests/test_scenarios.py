from __future__ import annotations

import json
from datetime import timedelta

from shared.enums import ProbePosition
from shared.wire import from_wire, to_wire
from simulator.scenarios import (
    OUT_DIR,
    SCENARIOS,
    CompressorFailureScenario,
    DeadZoneScenario,
    FreezeRiskScenario,
    NominalScenario,
    RefrigerantLossScenario,
)

# Keep the wire/ground-truth structural tests fast; the interesting
# scenario-specific behavior is checked with each scenario's own natural
# (possibly much longer) duration in the tests below.
SHORT_DURATION_MIN = 45.0


def test_every_scenario_yields_schema_valid_packets_that_wire_roundtrip() -> None:
    for cls in SCENARIOS.values():
        scenario = cls()
        packets = list(scenario.run(duration_min=SHORT_DURATION_MIN, dt_s=60.0))
        assert len(packets) > 0
        for packet in packets:
            restored = from_wire(to_wire(packet))
            assert restored == packet


def test_nominal_zero_minutes_out_of_band_and_duty_tracks_expected() -> None:
    gt = NominalScenario().ground_truth()
    assert gt["minutes_outside_band"] == 0

    duty = gt["trajectories"]["duty_pct"]
    expected = gt["trajectories"]["expected_duty_pct"]
    # Per-sample duty (a rolling window) and expected_duty_pct (an
    # instantaneous analytical baseline) diverge sharply for a few minutes
    # right when the truck arrives at a stop -- the window hasn't caught up
    # to the sudden change in conditions yet. That's a real, legitimate lag,
    # not an anomaly, so check the overall bias averages out to "a few
    # points" over the whole run rather than bounding every single sample.
    mean_diff = sum(duty) / len(duty) - sum(expected) / len(expected)
    assert abs(mean_diff) <= 5.0


def test_refrigerant_loss_duty_exceeds_expected_well_before_thermal_breach() -> None:
    gt = RefrigerantLossScenario().ground_truth()
    detect_t = gt["expected_first_detection_min"]
    breach_t = gt["expected_thermal_breach_min"]

    assert detect_t is not None
    # The scenario is designed so duty creep is visible days before any
    # thermal effect -- breach may not happen at all within duration_min.
    assert breach_t is None or (breach_t - detect_t) >= 60.0


def test_compressor_failure_zeroes_all_channels_after_unit_off() -> None:
    scenario = CompressorFailureScenario()
    packets = list(scenario.run(dt_s=60.0))
    failure_min = scenario.FAILURE_AT_MIN

    after_failure = [
        p for p in packets if (p.ts - packets[0].ts).total_seconds() / 60.0 > failure_min + 2.0
    ]
    assert after_failure
    for p in after_failure:
        assert p.power.compressor.i_rms == 0.0
        assert p.power.cond_fan.i_rms == 0.0
        assert p.power.evap_fan.i_rms == 0.0


def test_freeze_risk_crosses_lower_bound_on_vaccines_profile() -> None:
    gt = FreezeRiskScenario().ground_truth()
    assert gt["profile"] == "vaccines"
    assert gt["expected_freeze_breach_min"] is not None
    assert gt["expected_first_detection_min"] is not None
    assert gt["expected_first_detection_min"] < gt["expected_freeze_breach_min"]


def test_dead_zone_contiguous_timestamps_no_seq_gap_buffered_flagged() -> None:
    scenario = DeadZoneScenario()
    packets = list(scenario.run(dt_s=60.0))

    for prev, cur in zip(packets, packets[1:], strict=False):
        assert cur.seq == prev.seq + 1
        assert (cur.ts - prev.ts).total_seconds() == 60.0

    gt = scenario.ground_truth()
    window = gt["fault_windows"][0]
    start_ts = packets[0].ts + timedelta(minutes=window["start_min"])
    end_ts = packets[0].ts + timedelta(minutes=window["end_min"])
    outage_packets = [p for p in packets if start_ts <= p.ts < end_ts]
    assert outage_packets
    assert all(p.buffered for p in outage_packets)
    assert gt["expected_gap_in_record"] is False


def test_every_scenario_writes_ground_truth_with_expected_keys(tmp_path) -> None:
    required_keys = {
        "scenario",
        "profile",
        "duration_min",
        "fault_windows",
        "expected_first_detection_min",
        "expected_detection_cause",
    }
    for name, cls in SCENARIOS.items():
        scenario = cls()
        path = scenario.write_ground_truth(out_dir=tmp_path, duration_min=SHORT_DURATION_MIN)
        assert path.exists()
        assert path.name == f"{name}_ground_truth.json"

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert required_keys.issubset(data.keys())


def test_probe_positions_present_in_every_packet() -> None:
    scenario = NominalScenario()
    packet = next(iter(scenario.run(duration_min=SHORT_DURATION_MIN, dt_s=60.0)))
    positions = {c.pos for c in packet.cargo}
    assert positions == {
        ProbePosition.front,
        ProbePosition.rear_door,
        ProbePosition.top,
        ProbePosition.bottom,
    }


def test_out_dir_matches_module_constant() -> None:
    assert OUT_DIR.name == "out"
