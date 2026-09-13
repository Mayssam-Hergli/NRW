"""First-order lumped thermal model of the cargo compartment.

    dT/dt = (T_eff - T) / tau - cooling_delivered

The same equation drives an internal, unexposed control-reference channel
(used only for the thermostat, exactly the equation above with no offset)
and four displayed probe channels, each with its own steady-state offset
and its own tau multiplier, to capture that real compartments stratify.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.enums import ProbePosition
from shared.profiles import MissionProfile, get_profile
from simulator import config

_PROBES: tuple[ProbePosition, ...] = (
    ProbePosition.front,
    ProbePosition.rear_door,
    ProbePosition.top,
    ProbePosition.bottom,
)


@dataclass
class ThermalState:
    t_by_probe: dict[ProbePosition, float]
    compressor_on: bool
    cooling_capacity_frac: float
    door_open: bool


def stationary_capacity_frac(speed_kmh: float, ambient_c: float) -> float:
    """Cooling capacity multiplier from condenser-airflow loss while parked
    in the heat. Not applied inside ThermalSim.step() (which has no notion
    of vehicle speed) -- the orchestrating loop calls this and assigns the
    result to ThermalSim.cooling_capacity_frac before stepping.
    """
    if speed_kmh > config.STATIONARY_SPEED_THRESHOLD_KMH:
        return 1.0
    excess_c = max(0.0, ambient_c - config.CAPACITY_DEGRADE_AMBIENT_BASELINE_C)
    frac = 1.0 - config.CAPACITY_DEGRADE_PER_C * excess_c
    return max(config.MIN_STATIONARY_CAPACITY_FRAC, frac)


class ThermalSim:
    def __init__(self, profile: MissionProfile) -> None:
        spec = get_profile(profile)
        self.setpoint_c = (spec.min_c + spec.max_c) / 2.0
        self.tau_min = config.THERMAL_TAU_MIN
        self.cooling_capacity_frac = 1.0
        self.compressor_on = False

        self._t_ref = self.setpoint_c
        self._t_probe: dict[ProbePosition, float] = {
            probe: self.setpoint_c + config.PROBE_OFFSET_C[probe] for probe in _PROBES
        }

    def step(self, dt_s: float, effective_ambient_c: float, door_open: bool) -> ThermalState:
        dt_min = dt_s / 60.0

        if self._t_ref > self.setpoint_c + config.THERMOSTAT_HYSTERESIS_C:
            self.compressor_on = True
        elif self._t_ref < self.setpoint_c - config.THERMOSTAT_HYSTERESIS_C:
            self.compressor_on = False

        if door_open:
            tau_ref = self.tau_min / config.DOOR_OPEN_TAU_SPEEDUP
            cooling_ref = 0.0
        else:
            tau_ref = self.tau_min
            cooling_ref = (
                config.COOLING_POWER_C_PER_MIN * self.cooling_capacity_frac
                if self.compressor_on
                else 0.0
            )

        d_ref = (effective_ambient_c - self._t_ref) / tau_ref - cooling_ref
        self._t_ref += d_ref * dt_min

        t_by_probe: dict[ProbePosition, float] = {}
        for probe in _PROBES:
            mult = config.PROBE_TAU_MULT[probe]
            offset = config.PROBE_OFFSET_C[probe]
            target = effective_ambient_c + offset
            if door_open:
                # An open door creates turbulent mixing that overwhelms the
                # normal internal airflow pattern, so every probe relaxes
                # at the same rate during the event -- only their fixed
                # offsets differ. (Without this, front's short tau lets it
                # race past rear_door's higher target during the transient,
                # even though rear_door should be first to breach.)
                tau_p = tau_ref
                cooling_p = 0.0
            else:
                tau_p = tau_ref * mult
                # Cooling is divided by the same mult that scales tau_p, so
                # a probe's steady state always lands at (reference +
                # offset) regardless of its own tau -- only the approach
                # speed differs. (Physically: a probe closer to the
                # evaporator also sees more direct airflow, so faster
                # response and stronger cooling effect go together.)
                cooling_p = cooling_ref / mult
            t_p = self._t_probe[probe]
            d_p = (target - t_p) / tau_p - cooling_p
            self._t_probe[probe] = t_p + d_p * dt_min
            t_by_probe[probe] = self._t_probe[probe]

        return ThermalState(
            t_by_probe=t_by_probe,
            compressor_on=self.compressor_on,
            cooling_capacity_frac=self.cooling_capacity_frac,
            door_open=door_open,
        )
