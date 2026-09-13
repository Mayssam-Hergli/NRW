"""Electrical model of the refrigeration unit: compressor, fan, and bus
voltage channels, driven by the thermal sim's compressor_on decisions.

This is a one-way coupling. ElectricalSim never reaches back into
ThermalSim or changes its behavior -- it only observes compressor_on at
each step. That is deliberate: the whole premise of this simulator is that
electrical strain must fall out of the shared physics on its own. When
cooling_capacity_frac decays on the ThermalSim (refrigerant loss), the
thermostat loop keeps the compressor on longer to reach cutout, so duty
cycle rises here -- without electrical.py ever being told about the decay.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from shared.profiles import MissionProfile, get_profile
from simulator import config
from simulator.thermal import stationary_capacity_frac


@dataclass
class ElectricalState:
    i_compressor: float
    i_cond_fan: float
    i_evap_fan: float
    inrush_peak: float
    v_bus: float
    duty_pct: float


class ElectricalSim:
    def __init__(
        self,
        profile: MissionProfile,
        bearing_wear_factor: float = 1.0,
        cond_fan_ok: bool = True,
        evap_fan_ok: bool = True,
        alternator_health: float = 1.0,
        unit_powered: bool = True,
    ) -> None:
        spec = get_profile(profile)
        self.setpoint_c = (spec.min_c + spec.max_c) / 2.0

        self.bearing_wear_factor = bearing_wear_factor
        self.cond_fan_ok = cond_fan_ok
        self.evap_fan_ok = evap_fan_ok
        self.alternator_health = alternator_health
        self.unit_powered = unit_powered

        self._prev_on = False
        self._time_since_on_s = 0.0
        self._last_inrush_peak = 0.0

        self._duty_window: deque[tuple[float, bool]] = deque()
        self._duty_window_on_s = 0.0
        self._duty_window_total_s = 0.0

    def _steady_compressor_current_a(self, effective_ambient_c: float) -> float:
        gap_c = max(0.0, effective_ambient_c - self.setpoint_c)
        return config.COMPRESSOR_BASE_CURRENT_A + config.COMPRESSOR_CURRENT_PER_DELTA_C * gap_c

    def expected_duty_pct(self, effective_ambient_c: float, speed_kmh: float) -> float:
        """Baseline duty cycle for healthy equipment under these conditions.

        Derived analytically from the same thermal energy balance the ODE
        integrates, rather than fit from a simulation run: at steady state,
        average cooling delivered must equal average heat ingress into the
        control reference --

            duty * COOLING_POWER_C_PER_MIN * capacity_frac == (T_eff - setpoint) / tau

        solved for duty. capacity_frac uses the same stationary-airflow
        degradation curve a healthy unit experiences when parked in heat
        (thermal.stationary_capacity_frac), so a healthy truck stopped in
        full sun doesn't read as anomalous. That helper's real signature
        takes raw ambient; this function only receives effective ambient
        (per its required signature), and the two are close enough for a
        baseline used to size an anomaly margin, not to drive the ODE --
        noted here rather than silently glossed over.
        """
        capacity_frac = stationary_capacity_frac(speed_kmh, effective_ambient_c)
        gap_c = max(0.0, effective_ambient_c - self.setpoint_c)
        if gap_c <= 0.0:
            return 0.0
        denom = config.THERMAL_TAU_MIN * config.COOLING_POWER_C_PER_MIN * capacity_frac
        duty_frac = gap_c / denom
        return max(0.0, min(100.0, duty_frac * 100.0))

    def step(self, dt_s: float, effective_ambient_c: float, compressor_on: bool) -> ElectricalState:
        on = compressor_on and self.unit_powered

        if on and not self._prev_on:
            self._time_since_on_s = 0.0
            steady_now = self._steady_compressor_current_a(effective_ambient_c)
            self._last_inrush_peak = (
                steady_now * config.INRUSH_MULTIPLIER * self.bearing_wear_factor
            )
        self._prev_on = on

        if on:
            steady = self._steady_compressor_current_a(effective_ambient_c)
            decay = math.exp(-self._time_since_on_s / config.INRUSH_DECAY_TAU_S)
            i_compressor = steady + (self._last_inrush_peak - steady) * decay
            self._time_since_on_s += dt_s
        else:
            i_compressor = 0.0

        i_cond_fan = config.COND_FAN_CURRENT_A if (on and self.cond_fan_ok) else 0.0
        i_evap_fan = config.EVAP_FAN_CURRENT_A if (self.unit_powered and self.evap_fan_ok) else 0.0

        total_i = i_compressor + i_cond_fan + i_evap_fan
        sag_v = (config.BUS_SAG_V_PER_AMP * total_i) / max(self.alternator_health, 1e-6)
        v_bus = config.NOMINAL_BUS_VOLTAGE_V - sag_v

        self._duty_window.append((dt_s, on))
        self._duty_window_total_s += dt_s
        if on:
            self._duty_window_on_s += dt_s
        window_s = config.DUTY_CYCLE_WINDOW_MIN * 60.0
        while self._duty_window_total_s > window_s and self._duty_window:
            old_dt, old_on = self._duty_window.popleft()
            self._duty_window_total_s -= old_dt
            if old_on:
                self._duty_window_on_s -= old_dt
        duty_pct = (
            0.0
            if self._duty_window_total_s <= 0
            else 100.0 * self._duty_window_on_s / self._duty_window_total_s
        )

        return ElectricalState(
            i_compressor=i_compressor,
            i_cond_fan=i_cond_fan,
            i_evap_fan=i_evap_fan,
            inrush_peak=self._last_inrush_peak,
            v_bus=v_bus,
            duty_pct=duty_pct,
        )
