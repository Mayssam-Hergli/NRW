"""Every tunable number in the physics simulation, named and explained.

Nothing in route.py, ambient.py, or thermal.py should contain an inline
numeric literal that isn't a pure unit-conversion constant (e.g. 60 to go
from minutes to seconds). If a curve looks wrong, tune it here.
"""

from __future__ import annotations

from shared.enums import MissionProfile, ProbePosition

# --------------------------------------------------------------------------
# Route
# --------------------------------------------------------------------------

# Real roads between these towns are not straight lines (they curve around
# terrain, follow the coast, pass through towns). This inflates the
# great-circle distance between waypoints to an approximate road distance.
ROAD_DISTANCE_FACTOR = 1.25

CRUISE_SPEED_KMH = 80.0

# Gaussian jitter applied to cruise speed at each simulation step, so the
# speed trace looks like a real driver rather than a perfect cruise control.
SPEED_NOISE_STD_KMH = 2.5

# How fast the truck sheds/gains speed approaching and leaving a stop.
# Braking is quicker than a loaded truck pulling away.
DECEL_RATE_KMH_PER_MIN = 20.0
ACCEL_RATE_KMH_PER_MIN = 12.0

# Distance before a stop's waypoint at which the truck starts slowing down.
# Deliberately generous relative to the braking-distance implied by
# DECEL_RATE_KMH_PER_MIN, so the truck comes smoothly to rest at the stop
# rather than sitting at low speed for a long final stretch.
STOP_LOOKAHEAD_KM = 6.0

# Below this speed we treat the vehicle as "stopped" for state-machine
# purposes (snapping to exactly 0 rather than asymptotically approaching it).
STOP_SNAP_SPEED_KMH = 0.5

# (waypoint_index, duration_min): a 20-minute stop at Sfax (index 2) and a
# 15-minute stop at Gabès (index 3).
DEFAULT_OFFLOAD_STOPS: list[tuple[int, float]] = [(2, 20.0), (3, 15.0)]

# Simulation step used to build the route's time/position schedule.
ROUTE_DT_MIN = 0.1  # 6 seconds

# Fixed seed so the "mild noise" in cruise speed is reproducible run to run.
ROUTE_RNG_SEED = 20260913

# When the truck departs, as a 24h local hour. Feeds the ambient model.
DEFAULT_DEPARTURE_HOUR = 6.0

# --------------------------------------------------------------------------
# Ambient
# --------------------------------------------------------------------------

# Diurnal cycle shape: air temperature peaks at 15:00 local and bottoms out
# at 05:00. The two halves of the day are different lengths (10h rising,
# 14h falling), which is why this isn't a single symmetric sinusoid.
DIURNAL_PEAK_HOUR = 15.0
DIURNAL_TROUGH_HOUR = 5.0

# Climate reference points along the corridor: (name, night_c, day_c) in
# September, in the same north-to-south order as route.WAYPOINTS. Sfax and
# Gabès run hotter than a straight-line interpolation between Tunis and
# Médenine would predict -- this is the "plus an inland term" from the
# spec, expressed directly as climatology rather than a synthetic formula,
# since these towns don't lie on a simple coastal/inland axis.
WAYPOINT_NIGHT_DAY_C: dict[str, tuple[float, float]] = {
    "Tunis": (21.0, 32.0),
    "Sousse": (21.5, 32.5),
    "Sfax": (22.5, 34.5),
    "Gabès": (23.5, 37.5),
    "Médenine": (24.0, 39.0),
}

# Solar heating of the compartment peaks near solar noon, earlier than the
# air-temperature peak (air temperature lags solar input by a few hours --
# real meteorology, and it also gives the thermal model a cleaner forcing
# signal to lag behind in turn).
SOLAR_PEAK_HOUR = 13.0
# Half-width of the daylight solar-load bell curve; zero contribution
# outside SOLAR_PEAK_HOUR +/- this many hours.
SOLAR_HALF_WIDTH_HOURS = 6.5

# Extra effective ambient at solar peak while the vehicle is moving (some
# airflow still reaches the condenser and compartment skin).
SOLAR_LOAD_MOVING_MAX_C = 6.0
# Extra effective ambient at solar peak while stationary: reefer condensers
# depend on vehicle motion / their own fan for airflow, so a parked truck
# in full sun runs hotter than a moving one at the same air temperature.
SOLAR_LOAD_STATIONARY_MAX_C = 11.0

# Speed below which the vehicle counts as "stationary" for solar-load and
# condenser-airflow purposes.
STATIONARY_SPEED_THRESHOLD_KMH = 2.0

# --------------------------------------------------------------------------
# Thermal
# --------------------------------------------------------------------------

# Thermal time constant of the loaded compartment with cooling off, in
# minutes. This is ground truth for the simulator only -- in production M1
# estimates tau online by fitting the warming curve during door-open events.
THERMAL_TAU_MIN = 120.0

# Compressor thermostat hysteresis band around the setpoint (the profile
# band's midpoint), in Celsius. Profile-dependent, not a single constant:
# FRONT's own dynamic overshoot below setpoint each cycle (its -0.9C offset
# plus its halved tau and doubled cooling gain -- see PROBE_OFFSET_C /
# PROBE_TAU_MULT below -- causes it to swing well past where the reference
# channel itself would stop) is close to a *fixed absolute* quantity,
# essentially independent of which profile is loaded, because it's driven
# by these same shared constants regardless of the band. A single global
# 0.5C value was tuned against the 10C-wide profiles and leaves almost no
# margin on a 6C band, and none at all on a 4C one -- measured empirically
# (simulator/thermal.py, healthy cycling, no fault):
#
#   profile               band   front_min   margin to floor (at 0.5C)
#   controlled_room_temp  10C    17.33 C     +2.33 C
#   pharma_frozen         10C   -22.67 C     +2.33 C
#   pharma_refrigerated    6C     2.33 C     +0.33 C
#   vaccines               6C     2.33 C     +0.33 C
#   fresh_produce          4C    -0.67 C     -0.67 C  (already past the floor)
#
# fresh_produce's FRONT probe crosses its own band's lower bound during
# ordinary, fault-free cycling at the default hysteresis -- not a fault
# scenario artifact. Narrowed per profile below to restore real margin on
# the two 6C-band profiles and correct the outright breach on the 4C one;
# the two 10C-band profiles already had comfortable margin and are
# unchanged. This does not fully eliminate FRONT's undershoot (that's
# driven mostly by its offset and response speed, not hysteresis alone --
# narrowing hysteresis to zero on fresh_produce still bottoms out around
# +0.5C, bounded by FRONT's own -0.9C offset), it only restores the margin
# a 0.5C-tuned hysteresis assumed was there.
THERMOSTAT_HYSTERESIS_C: dict[MissionProfile, float] = {
    MissionProfile.pharma_refrigerated: 0.2,
    MissionProfile.pharma_frozen: 0.5,
    MissionProfile.controlled_room_temp: 0.5,
    MissionProfile.vaccines: 0.2,
    MissionProfile.fresh_produce: 0.1,
}

# Cooling power expressed in the same units as the ODE's other terms:
# degrees C per minute the compressor can pull the reference channel down
# by, at full (1.0) cooling_capacity_frac. Sized with headroom over the
# worst heat ingress this route/schedule produces, so a healthy unit can
# hold the band; a degraded cooling_capacity_frac (step 2) can still fail to.
COOLING_POWER_C_PER_MIN = 0.55

# Door open removes cooling and lets outside air mix in directly, which
# raises heat ingress well above the sealed-compartment rate. Modeled as a
# reduction of the effective tau (faster equilibration toward ambient).
DOOR_OPEN_TAU_SPEEDUP = 3.0

# Per-probe steady-state offset (Celsius, relative to the control
# reference) and tau multiplier (relative to THERMAL_TAU_MIN), capturing
# compartment stratification. Front sits near the evaporator: coldest and
# fastest to respond. Rear door is warmest and slowest -- first to breach.
PROBE_OFFSET_C: dict[ProbePosition, float] = {
    ProbePosition.front: -0.9,
    ProbePosition.top: -0.2,
    ProbePosition.bottom: -0.5,
    ProbePosition.rear_door: 1.3,
}
PROBE_TAU_MULT: dict[ProbePosition, float] = {
    ProbePosition.front: 0.5,
    ProbePosition.top: 0.9,
    ProbePosition.bottom: 1.0,
    ProbePosition.rear_door: 1.6,
}

# --- Stationary-in-heat cooling capacity degradation ---
# Not applied inside ThermalSim.step() (which only knows dt/ambient/door);
# the orchestrating loop (preview.py, later scenarios) calls
# thermal.stationary_capacity_frac(speed, ambient) and assigns the result
# to ThermalSim.cooling_capacity_frac before stepping.

# Ambient below this, a parked reefer's condenser isn't meaningfully
# airflow-starved.
CAPACITY_DEGRADE_AMBIENT_BASELINE_C = 25.0
# Fractional cooling capacity lost per degree C of ambient above the
# baseline while stationary.
CAPACITY_DEGRADE_PER_C = 0.02
# Even parked in extreme heat, some natural convection still reaches the
# condenser, so capacity never degrades below this floor from this effect
# alone.
MIN_STATIONARY_CAPACITY_FRAC = 0.5

# --------------------------------------------------------------------------
# Electrical
# --------------------------------------------------------------------------

# Compressor RMS current model: a base draw plus a term proportional to how
# hard it's working, i.e. how far effective ambient sits above setpoint.
COMPRESSOR_BASE_CURRENT_A = 3.0
COMPRESSOR_CURRENT_PER_DELTA_C = 0.055

# Inrush peak at turn-on, as a multiple of that moment's steady current, at
# a healthy (1.0) bearing_wear_factor. "Several times" per spec; consistent
# with real single-phase compressor locked-rotor current.
INRUSH_MULTIPLIER = 5.0
# How fast the inrush spike decays back to steady current once running.
INRUSH_DECAY_TAU_S = 1.0
# The spike is treated as fully settled after this many seconds -- about
# 5 tau, ~99% decayed.
INRUSH_STARTUP_WINDOW_S = 5.0

# Condenser fan runs only while the compressor is actively running (it
# exists to reject heat at the condenser coil). Evaporator fan runs
# continuously whenever the unit has power, circulating box air even
# between compressor cycles.
COND_FAN_CURRENT_A = 0.9
EVAP_FAN_CURRENT_A = 0.7

# Bus voltage sags under load, proportional to total instantaneous current;
# alternator_health divides into the sag term, so a worse alternator
# produces a deeper sag for the same current draw.
NOMINAL_BUS_VOLTAGE_V = 24.0
BUS_SAG_V_PER_AMP = 0.15

# Rolling window over which duty cycle (fraction of time compressor_on) is
# computed. This is the feature refrigerant loss shows up in first.
DUTY_CYCLE_WINDOW_MIN = 15.0

# For the lead-time acceptance check: how far actual duty must exceed
# expected_duty_pct, in percentage points, before it counts as a
# detectable anomaly (as opposed to ordinary hysteresis-band noise).
DUTY_ANOMALY_MARGIN_PCT = 8.0
