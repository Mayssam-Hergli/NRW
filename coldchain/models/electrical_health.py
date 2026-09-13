"""M2 -- electrical health, rule-based.

Detects the electrical-domain faults from PROJECT.md's fault catalogue by
watching the same signals a real device would report on TelemetryPacket:
compressor duty cycle, fan currents, bus voltage, and inrush peak. No
Isolation Forest, no numpy/sklearn -- there's no ML dependency anywhere in
this project, and the acceptance bar (flag refrigerant_loss before any
thermal breach, zero false positives on nominal) is met by the same
baseline-normalised, EWMA-smoothed duty residual already proven in
tests/test_electrical.py::test_lead_time_duty_anomaly_precedes_thermal_breach
-- this module is that logic, reshaped to consume packets one at a time
instead of running inside a test loop.

Never threshold raw duty_pct: expected_duty_pct() already rises with
ambient/speed for a healthy unit, so only the residual against that
baseline is a fault signal.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from shared.enums import CompressorState, FaultCause
from shared.schema import TelemetryPacket
from simulator import config

FAN_ZERO_EPSILON_A = 0.05
UNIT_OFF_SUSTAIN_MIN = 3.0
BEARING_WEAR_MARGIN_FRAC = 0.15
VOLTAGE_SAG_THRESHOLD_V = config.NOMINAL_BUS_VOLTAGE_V - 3.0
SMOOTH_WINDOW_MIN = 45.0

# Wider than config.DUTY_ANOMALY_MARGIN_PCT (8pp): that constant is tuned in
# tests/test_electrical.py against a fixed-speed, fixed-ambient bench run.
# On an actual route, expected_duty_pct() reacts instantly to a stop/go
# speed change (capacity_frac jumps) while the real, smoothed duty_pct
# carries thermal/duty-window inertia through the same transition -- nominal
# spikes to ~15pp residual on ordinary route stops. 18pp clears that with
# margin while still catching refrigerant_loss's much larger, sustained
# residual well ahead of any thermal breach.
DUTY_ANOMALY_MARGIN_PCT = 18.0


def _expected_inrush_a(ambient_c: float, setpoint_c: float) -> float:
    """Healthy inrush peak at this ambient, from the same steady-current
    formula ElectricalSim uses internally (COMPRESSOR_BASE_CURRENT_A +
    per-degree term over setpoint, times INRUSH_MULTIPLIER). Needed because
    a single captured baseline drifts with ambient over a multi-hour route
    -- normalizing against ambient is what expected_duty_pct already does
    for duty, and bearing wear needs the same treatment.
    """
    gap_c = max(0.0, ambient_c - setpoint_c)
    steady = config.COMPRESSOR_BASE_CURRENT_A + config.COMPRESSOR_CURRENT_PER_DELTA_C * gap_c
    return steady * config.INRUSH_MULTIPLIER


@dataclass
class ElectricalHealthResult:
    cause: FaultCause | None
    evidence: dict[str, float]


@dataclass
class ElectricalHealthMonitor:
    """One instance per device. Feed packets in chronological order."""

    dt_min: float = 1.0
    _smoothed_duty: deque[float] = field(init=False)
    _smoothed_v_bus: deque[float] = field(init=False)
    _evap_zero_min: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        n = max(1, int(SMOOTH_WINDOW_MIN / self.dt_min))
        self._smoothed_duty = deque(maxlen=n)
        self._smoothed_v_bus = deque(maxlen=n)

    def update(self, packet: TelemetryPacket, expected_duty_pct: float) -> ElectricalHealthResult:
        power = packet.power
        actual_duty = power.compressor.duty_pct or 0.0
        self._smoothed_duty.append(actual_duty)
        smoothed = sum(self._smoothed_duty) / len(self._smoothed_duty)
        residual_pp = smoothed - expected_duty_pct

        # v_bus is an instantaneous end-of-step reading, and the 60s sample
        # interval is coarse relative to the ~1s inrush decay -- a sample
        # that happens to land exactly on a compressor turn-on instant
        # briefly reads near-inrush current, which is normal every cycle,
        # not a sag fault. Smooth over the same trailing window as duty so
        # a real sustained sag (many cycles) is still caught.
        self._smoothed_v_bus.append(power.v_bus)
        smoothed_v_bus = sum(self._smoothed_v_bus) / len(self._smoothed_v_bus)

        evidence: dict[str, float] = {
            "duty_pct": actual_duty,
            "expected_duty_pct": round(expected_duty_pct, 2),
            "residual_pp": round(residual_pp, 2),
            "v_bus": round(smoothed_v_bus, 2),
        }

        if power.state == CompressorState.RUN and power.cond_fan.i_rms <= FAN_ZERO_EPSILON_A:
            return ElectricalHealthResult(FaultCause.fan_failure, evidence)

        if power.evap_fan.i_rms <= FAN_ZERO_EPSILON_A:
            self._evap_zero_min += self.dt_min
        else:
            self._evap_zero_min = 0.0
        if self._evap_zero_min >= UNIT_OFF_SUSTAIN_MIN:
            evidence["mins"] = self._evap_zero_min
            return ElectricalHealthResult(FaultCause.unit_off, evidence)

        if (
            len(self._smoothed_v_bus) == self._smoothed_v_bus.maxlen
            and smoothed_v_bus < VOLTAGE_SAG_THRESHOLD_V
        ):
            return ElectricalHealthResult(FaultCause.voltage_sag, evidence)

        inrush = power.compressor.inrush_peak
        if inrush and packet.band is not None:
            setpoint_c = (packet.band.min_c + packet.band.max_c) / 2.0
            expected_inrush = _expected_inrush_a(packet.ambient_c, setpoint_c)
            if expected_inrush > 0 and inrush > expected_inrush * (1.0 + BEARING_WEAR_MARGIN_FRAC):
                evidence["dev_pp"] = round(100.0 * (inrush / expected_inrush - 1.0), 1)
                return ElectricalHealthResult(FaultCause.bearing_wear, evidence)

        if len(self._smoothed_duty) == self._smoothed_duty.maxlen and (
            residual_pp > DUTY_ANOMALY_MARGIN_PCT
        ):
            evidence["dev_pp"] = round(residual_pp, 1)
            return ElectricalHealthResult(FaultCause.refrigerant_loss, evidence)

        return ElectricalHealthResult(None, evidence)
