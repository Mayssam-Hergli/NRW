"""Scores M1ThermalForecast against the simulator's own ground truth.

Uses simulator.scenarios directly (not files under simulator/out/, which are
gitignored build artifacts) -- ground_truth() and run() are the same calls
those files are written from.
"""

from __future__ import annotations

from models.m1_thermal import PRIOR_CONFIDENCE, PRIOR_TAU_MIN, M1ThermalForecast
from shared.enums import ProbePosition
from shared.profiles import get_profile
from simulator.config import THERMAL_TAU_MIN
from simulator.scenarios import (
    DeadZoneScenario,
    DoorOpenScenario,
    FreezeRiskScenario,
    NominalScenario,
    RefrigerantLossScenario,
)

DT_S = 60.0


def _find_breach_min(scenario, duration_min: float | None = None, use_bottom: bool = False):
    """First minute any probe (or, for freeze_risk, specifically BOTTOM --
    see FreezeRiskScenario's own docstring on why FRONT is too noisy to use
    as the fault reference there) crosses the profile band."""
    spec = get_profile(scenario.profile)
    for i, packet in enumerate(scenario.run(duration_min=duration_min, dt_s=DT_S)):
        if use_bottom:
            bottom = next(c.t_c for c in packet.cargo if c.pos == ProbePosition.bottom)
            if bottom < spec.min_c:
                return i
        else:
            worst = max(c.t_c for c in packet.cargo)
            coldest = min(c.t_c for c in packet.cargo)
            if worst > spec.max_c or coldest < spec.min_c:
                return i
    return None


def test_nominal_never_forecasts_a_breach() -> None:
    scenario = NominalScenario()
    m1 = M1ThermalForecast()
    for packet in scenario.run(dt_s=DT_S):
        result = m1.update(packet)
        assert result.minutes_to_breach is None
        assert all(v is None for v in result.per_probe.values())


def test_door_open_countdown_appears_before_breach_and_shortens() -> None:
    scenario = DoorOpenScenario()
    breach_min = _find_breach_min(scenario)
    assert breach_min is not None

    m1 = M1ThermalForecast()
    countdowns = []
    for i, packet in enumerate(scenario.run(dt_s=DT_S)):
        if i > breach_min:
            break
        result = m1.update(packet)
        if result.minutes_to_breach is not None:
            countdowns.append(result.minutes_to_breach)

    assert len(countdowns) >= 2, "expected a countdown to appear before the breach"
    assert all(b <= a + 1e-6 for a, b in zip(countdowns, countdowns[1:], strict=False)), (
        f"countdown did not shorten monotonically: {countdowns}"
    )


def test_mae_under_15_minutes_across_breaching_scenarios() -> None:
    """"Predicted breach time" is evaluated once per scenario: the first
    forecast in the scenario's true fault direction (a scenario can produce
    a stray opposite-direction blip on a single noisy probe -- e.g. FRONT's
    own fast cycling briefly reading as "trending toward freeze" during a
    refrigerant_loss run that has nothing to do with freezing -- which is a
    real, separate false-positive-rate concern, not part of "how accurate is
    the breach forecast"). compressor_failure is excluded: in this
    simulator, ThermalSim's thermostat is entirely independent of
    ElectricalSim's unit_powered flag, so a "unit off" fault never actually
    stops cooling thermally and the scenario has no real breach to score
    against, at any duration.
    """
    cases = [
        ("door_open", DoorOpenScenario(), None, False, "upper"),
        ("refrigerant_loss", RefrigerantLossScenario(), 6000.0, False, "upper"),
        ("freeze_risk", FreezeRiskScenario(), None, True, "lower"),
    ]
    errors = []
    for name, scenario, duration, use_bottom, direction in cases:
        breach_min = _find_breach_min(scenario, duration_min=duration, use_bottom=use_bottom)
        assert breach_min is not None, f"{name}: expected a real breach at this duration"

        m1 = M1ThermalForecast()
        for i, packet in enumerate(scenario.run(duration_min=duration, dt_s=DT_S)):
            if i > breach_min:
                break
            result = m1.update(packet)
            if result.minutes_to_breach is not None and result.breach_bound == direction:
                predicted = i + result.minutes_to_breach
                errors.append(abs(predicted - breach_min))
                break
        else:
            raise AssertionError(f"{name}: no correct-direction forecast before breach")

    mae = sum(errors) / len(errors)
    print(f"\nM1 MAE at first correct-direction detection: {mae:.2f} min (n={len(errors)})")
    assert mae < 15.0


def test_tau_converges_within_one_door_event() -> None:
    """Checked once the first door event has *closed* again, not at the
    instant it opens -- RLS only gets a data point once it has both a
    door-open sample and the previous one to difference against, so the
    very first door-open packet is still just the prior."""
    scenario = DoorOpenScenario()
    m1 = M1ThermalForecast()
    tau_after_event: float | None = None
    confidence_after_event: float | None = None
    seen_open = False
    for packet in scenario.run(dt_s=DT_S):
        result = m1.update(packet)
        if packet.door.open:
            seen_open = True
        elif seen_open:
            tau_after_event = result.tau_estimate_min
            confidence_after_event = result.tau_confidence
            break

    assert tau_after_event is not None
    rel_error = abs(tau_after_event - THERMAL_TAU_MIN) / THERMAL_TAU_MIN
    print(f"\nM1 tau after one door event: {tau_after_event:.1f} min "
          f"(true {THERMAL_TAU_MIN} min, {rel_error:.1%} error)")
    assert rel_error < 0.20
    assert confidence_after_event > PRIOR_CONFIDENCE


def test_prior_before_any_door_event() -> None:
    scenario = DoorOpenScenario()
    m1 = M1ThermalForecast()
    for packet in scenario.run(dt_s=DT_S):
        if packet.door.open:
            break
        result = m1.update(packet)
        assert result.tau_estimate_min == PRIOR_TAU_MIN
        assert result.tau_confidence == PRIOR_CONFIDENCE


def test_rear_door_breaches_sooner_than_front_on_warming_run() -> None:
    scenario = DoorOpenScenario()
    m1 = M1ThermalForecast()
    for packet in scenario.run(dt_s=DT_S):
        result = m1.update(packet)
        rear = result.per_probe[ProbePosition.rear_door]
        front = result.per_probe[ProbePosition.front]
        if rear is not None and front is not None:
            assert rear < front
            return
    raise AssertionError("both probes never produced a forecast in this run")


def test_freeze_risk_lower_bound_countdown_before_2c_crossed() -> None:
    scenario = FreezeRiskScenario()
    breach_min = _find_breach_min(scenario, use_bottom=True)
    assert breach_min is not None

    m1 = M1ThermalForecast()
    saw_lower_countdown = False
    for i, packet in enumerate(scenario.run(dt_s=DT_S)):
        if i > breach_min:
            break
        result = m1.update(packet)
        if result.minutes_to_breach is not None and result.breach_bound == "lower":
            saw_lower_countdown = True
            break

    assert saw_lower_countdown


def _tau_after_first_door_event(scenario) -> float | None:
    m1 = M1ThermalForecast()
    seen_open = False
    for packet in scenario.run(dt_s=DT_S):
        result = m1.update(packet)
        if packet.door.open:
            seen_open = True
        elif seen_open:
            return result.tau_estimate_min
    return None


def test_buffered_gap_does_not_corrupt_tau_estimate() -> None:
    tau_clean = _tau_after_first_door_event(DoorOpenScenario())
    tau_dirty = _tau_after_first_door_event(DeadZoneScenario())

    assert tau_clean is not None
    assert tau_dirty is not None
    rel_error = abs(tau_dirty - tau_clean) / tau_clean
    assert rel_error < 0.20


def test_rising_ambient_forecast_shortens_the_countdown() -> None:
    """Uses refrigerant_loss's slow, stable trend rather than door_open's
    first noisy instant (door-open physics mode's RLS is still just the
    prior on its very first sample, which isn't a meaningful place to
    compare two forecasting modes against each other)."""
    scenario = RefrigerantLossScenario()
    m1_constant = M1ThermalForecast()
    m1_forecast = M1ThermalForecast()

    constant_result = None
    forecast_result = None
    for packet in scenario.run(duration_min=6000.0, dt_s=DT_S):
        r_const = m1_constant.update(packet)
        rising = [packet.ambient_c + 0.2 * k for k in range(1, 241)]
        r_fore = m1_forecast.update(packet, ambient_forecast=rising)
        if (
            r_const.minutes_to_breach is not None
            and r_fore.minutes_to_breach is not None
            and r_const.breach_bound == "upper"
            and r_fore.breach_bound == "upper"
        ):
            constant_result = r_const.minutes_to_breach
            forecast_result = r_fore.minutes_to_breach
            break

    assert constant_result is not None
    assert forecast_result is not None
    assert forecast_result < constant_result


def test_state_size_stays_bounded_over_a_nine_hour_run() -> None:
    scenario = DoorOpenScenario()
    m1 = M1ThermalForecast()
    max_history_len = 0
    for packet in scenario.run(duration_min=9 * 60.0, dt_s=DT_S):
        m1.update(packet)
        for hist in m1._history.values():  # noqa: SLF001
            max_history_len = max(max_history_len, len(hist))

    from models.m1_thermal import TREND_WINDOW_SAMPLES

    assert max_history_len == TREND_WINDOW_SAMPLES
    # RLS state per probe never grows either -- it's always exactly 5 floats
    for rls in m1._door_rls.values():  # noqa: SLF001
        assert isinstance(rls.a, float)
        assert isinstance(rls.p00, float)
