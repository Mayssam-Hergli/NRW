from __future__ import annotations

from collections import deque

from shared.enums import ProbePosition
from shared.profiles import MissionProfile, get_profile
from simulator import config
from simulator.electrical import ElectricalSim
from simulator.thermal import ThermalSim

PROFILE = MissionProfile.pharma_refrigerated


def _settle_on(sim: ElectricalSim, ambient_c: float, seconds: int = 20):
    state = None
    for _ in range(seconds):
        state = sim.step(1.0, ambient_c, compressor_on=True)
    return state


def test_compressor_current_zero_when_off_nonzero_when_on() -> None:
    sim = ElectricalSim(PROFILE)
    off_state = sim.step(60.0, 30.0, compressor_on=False)
    assert off_state.i_compressor == 0.0
    on_state = sim.step(60.0, 30.0, compressor_on=True)
    assert on_state.i_compressor > 0.0


def test_steady_current_higher_at_higher_ambient() -> None:
    sim_hot = ElectricalSim(PROFILE)
    sim_cold = ElectricalSim(PROFILE)
    hot_state = _settle_on(sim_hot, 42.0)
    cold_state = _settle_on(sim_cold, 25.0)
    assert hot_state.i_compressor > cold_state.i_compressor


def test_inrush_peak_above_steady_and_decays_within_window() -> None:
    sim = ElectricalSim(PROFILE)
    sim.step(1.0, 30.0, compressor_on=False)
    at_transition = sim.step(1.0, 30.0, compressor_on=True)
    steady = sim._steady_compressor_current_a(30.0)  # noqa: SLF001 -- test-only introspection

    assert at_transition.i_compressor > steady
    assert at_transition.inrush_peak > steady

    settled = None
    for _ in range(int(config.INRUSH_STARTUP_WINDOW_S)):
        settled = sim.step(1.0, 30.0, compressor_on=True)
    assert abs(settled.i_compressor - steady) < 0.05 * steady


def test_bearing_wear_raises_inrush_but_not_steady_current() -> None:
    sim_healthy = ElectricalSim(PROFILE, bearing_wear_factor=1.0)
    sim_worn = ElectricalSim(PROFILE, bearing_wear_factor=1.4)

    healthy_at_on = sim_healthy.step(1.0, 32.0, compressor_on=True)
    worn_at_on = sim_worn.step(1.0, 32.0, compressor_on=True)
    ratio = worn_at_on.inrush_peak / healthy_at_on.inrush_peak
    assert 1.35 <= ratio <= 1.45

    healthy_settled = _settle_on(sim_healthy, 32.0)
    worn_settled = _settle_on(sim_worn, 32.0)
    assert abs(healthy_settled.i_compressor - worn_settled.i_compressor) < 0.01


def test_bus_voltage_sags_during_inrush_recovers_and_alternator_health_deepens_it() -> None:
    sim = ElectricalSim(PROFILE)
    sim.step(1.0, 32.0, compressor_on=False)
    at_transition = sim.step(1.0, 32.0, compressor_on=True)
    sag_at_transition = config.NOMINAL_BUS_VOLTAGE_V - at_transition.v_bus

    settled = _settle_on(sim, 32.0)
    sag_settled = config.NOMINAL_BUS_VOLTAGE_V - settled.v_bus

    assert sag_at_transition > sag_settled
    assert settled.v_bus < config.NOMINAL_BUS_VOLTAGE_V

    sim_good = ElectricalSim(PROFILE, alternator_health=1.0)
    sim_bad = ElectricalSim(PROFILE, alternator_health=0.6)
    good_state = sim_good.step(1.0, 32.0, compressor_on=True)
    bad_state = sim_bad.step(1.0, 32.0, compressor_on=True)
    assert bad_state.v_bus < good_state.v_bus


def test_cond_fan_failure_isolated_from_compressor() -> None:
    sim = ElectricalSim(PROFILE, cond_fan_ok=False)
    state = sim.step(1.0, 32.0, compressor_on=True)
    assert state.i_cond_fan == 0.0
    assert state.i_compressor > 0.0


def test_unit_powered_false_zeroes_all_channels() -> None:
    sim = ElectricalSim(PROFILE, unit_powered=False)
    state = sim.step(1.0, 32.0, compressor_on=True)
    assert state.i_compressor == 0.0
    assert state.i_cond_fan == 0.0
    assert state.i_evap_fan == 0.0


def _run_duty(ambient_c: float, capacity_frac: float, hours: float):
    thermal = ThermalSim(PROFILE)
    thermal.cooling_capacity_frac = capacity_frac
    elec = ElectricalSim(PROFILE)
    cargo_temps = []
    duty_samples = []
    steps = int(hours * 60)
    for _ in range(steps):
        t_state = thermal.step(60.0, ambient_c, door_open=False)
        state = elec.step(60.0, ambient_c, compressor_on=t_state.compressor_on)
        cargo_temps.append(t_state.t_by_probe[ProbePosition.bottom])
        duty_samples.append(state.duty_pct)
    mean_cargo = sum(cargo_temps) / len(cargo_temps)
    # A single end-of-run snapshot of the rolling duty window is noisy: the
    # window (15 min) doesn't divide evenly into the compressor's natural
    # cycle period, so where the window happens to end shifts the reading.
    # Average over the settled second half of the run instead.
    settled = duty_samples[len(duty_samples) // 2 :]
    mean_duty = sum(settled) / len(settled)
    return mean_duty, mean_cargo


def test_duty_cycle_higher_at_high_ambient_than_low() -> None:
    duty_hot, _ = _run_duty(38.0, 1.0, hours=3)
    duty_cold, _ = _run_duty(26.0, 1.0, hours=3)
    assert duty_hot > duty_cold


def test_degraded_capacity_raises_duty_without_moving_cargo_temp() -> None:
    ambient_c = 34.0  # moderate: leaves headroom at both capacity levels
    duty_healthy, mean_healthy = _run_duty(ambient_c, 1.0, hours=6)
    duty_degraded, mean_degraded = _run_duty(ambient_c, 0.75, hours=6)

    assert duty_degraded > duty_healthy + 5.0
    assert abs(mean_degraded - mean_healthy) < 0.5


def test_lead_time_duty_anomaly_precedes_thermal_breach() -> None:
    """The key claim the whole product rests on: electrical strain shows up
    well before the thermal effect. Decays cooling_capacity_frac gradually
    (as refrigerant loss would) until cargo eventually breaches band, and
    checks that a duty-cycle anomaly (actual duty over expected_duty_pct by
    a detectable margin) was visible at least an hour earlier.
    """
    profile = PROFILE
    spec = get_profile(profile)
    ambient_c = 34.0
    speed_kmh = 80.0  # moving: keeps expected_duty_pct off its stationary branch

    thermal = ThermalSim(profile)
    elec = ElectricalSim(profile)

    dt_s = 60.0
    dt_min = dt_s / 60.0
    decay_span_min = 20 * 60.0  # ramp capacity down over 20 simulated hours
    min_capacity_frac = 0.3
    max_run_min = 30 * 60.0

    # The 15-minute rolling duty_pct window only spans ~1.7 compressor
    # cycles at this operating point (cycle period ~9 min), so it carries
    # real cycle-to-cycle noise of roughly +/-10 points that has nothing to
    # do with any fault. A real anomaly detector would never alarm off one
    # noisy sample -- smooth over a longer trailing buffer (several cycles)
    # before comparing to the margin, same as production logic would.
    smooth_min = 45.0
    smooth_buffer: deque[float] = deque(maxlen=int(smooth_min / dt_min))

    t_min = 0.0
    breach_t: float | None = None
    anomaly_t: float | None = None

    while t_min <= max_run_min:
        progress = min(1.0, t_min / decay_span_min)
        thermal.cooling_capacity_frac = 1.0 - progress * (1.0 - min_capacity_frac)

        t_state = thermal.step(dt_s, ambient_c, door_open=False)
        e_state = elec.step(dt_s, ambient_c, compressor_on=t_state.compressor_on)
        expected = elec.expected_duty_pct(ambient_c, speed_kmh)
        smooth_buffer.append(e_state.duty_pct)

        buffer_full = t_min >= config.DUTY_CYCLE_WINDOW_MIN + smooth_min
        if buffer_full and anomaly_t is None:
            smoothed_duty = sum(smooth_buffer) / len(smooth_buffer)
            if (smoothed_duty - expected) > config.DUTY_ANOMALY_MARGIN_PCT:
                anomaly_t = t_min

        worst_c = max(t_state.t_by_probe.values())
        if breach_t is None and worst_c > spec.max_c:
            breach_t = t_min
            break

        t_min += dt_min

    assert breach_t is not None, "expected a thermal breach within the run"
    assert anomaly_t is not None, "expected a detectable duty anomaly before the breach"

    lead_time_min = breach_t - anomaly_t
    print(
        f"\nlead time: {lead_time_min:.0f} min "
        f"(duty anomaly at t={anomaly_t:.0f}min, thermal breach at t={breach_t:.0f}min)"
    )
    assert lead_time_min >= 60.0


def test_expected_duty_tracks_actual_across_ambient_range() -> None:
    for ambient_c in (26.0, 30.0, 34.0, 38.0, 42.0):
        duty, _ = _run_duty(ambient_c, 1.0, hours=6)
        elec = ElectricalSim(PROFILE)
        expected = elec.expected_duty_pct(ambient_c, speed_kmh=80.0)
        assert abs(duty - expected) <= 8.0
