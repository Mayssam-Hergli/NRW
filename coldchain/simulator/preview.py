"""Runs one full journey and writes simulator/out/preview.csv.

Not a scenario driver (no faults, no electrical model, no MQTT -- those are
later steps) -- just the physical simulation this task built, run end to
end so the curves can be eyeballed.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from shared.enums import ProbePosition
from shared.profiles import MissionProfile, get_profile
from simulator import config
from simulator.ambient import ambient_c, effective_ambient_c
from simulator.electrical import ElectricalSim
from simulator.route import Route
from simulator.thermal import ThermalSim, stationary_capacity_frac

OUT_DIR = Path(__file__).parent / "out"
OUT_CSV = OUT_DIR / "preview.csv"

STEP_S = 60.0
MISSION_PROFILE = MissionProfile.pharma_refrigerated
DEPARTURE_HOUR = config.DEFAULT_DEPARTURE_HOUR

# Simulate a door-open event during the Sfax stop, since a real driver often
# opens the doors while stopped -- gives the preview something interesting
# to show for the door_open column beyond always-False.
DOOR_OPEN_DURING_STOP_MIN = (5.0, 12.0)  # minutes into the stop


def run(inject_door_event: bool = True) -> dict:
    route = Route()
    sim = ThermalSim(MISSION_PROFILE)
    elec = ElectricalSim(MISSION_PROFILE)
    spec = get_profile(MISSION_PROFILE)

    rows = []
    t = 0.0
    dt_min = STEP_S / 60.0

    # Any stationary period after the initial departure counts as "a stop"
    # for this purpose -- the truck only stands still at the two configured
    # offload stops (plus a single instant at t=0 before it pulls away).
    stop_started_t: float | None = None

    while t <= route.duration_min:
        point = route.position_at(t)
        air = ambient_c(t, point, DEPARTURE_HOUR)
        eff = effective_ambient_c(t, point, DEPARTURE_HOUR)

        door_open = False
        if inject_door_event and point.speed_kmh == 0.0 and t > 0.0:
            if stop_started_t is None:
                stop_started_t = t
            elapsed_in_stop = t - stop_started_t
            door_start, door_end = DOOR_OPEN_DURING_STOP_MIN
            door_open = door_start <= elapsed_in_stop <= door_end
        else:
            stop_started_t = None

        sim.cooling_capacity_frac = stationary_capacity_frac(point.speed_kmh, air)
        state = sim.step(STEP_S, eff, door_open=door_open)
        e_state = elec.step(STEP_S, eff, compressor_on=state.compressor_on)
        expected_duty = elec.expected_duty_pct(eff, point.speed_kmh)

        rows.append(
            {
                "t_min": round(t, 2),
                "lat": round(point.lat, 5),
                "lon": round(point.lon, 5),
                "speed_kmh": round(point.speed_kmh, 2),
                "ambient_c": round(air, 2),
                "eff_ambient_c": round(eff, 2),
                "t_front": round(state.t_by_probe[ProbePosition.front], 3),
                "t_rear_door": round(state.t_by_probe[ProbePosition.rear_door], 3),
                "compressor_on": state.compressor_on,
                "door_open": state.door_open,
                "i_compressor": round(e_state.i_compressor, 3),
                "i_cond_fan": round(e_state.i_cond_fan, 3),
                "i_evap_fan": round(e_state.i_evap_fan, 3),
                "inrush_peak": round(e_state.inrush_peak, 3),
                "v_bus": round(e_state.v_bus, 3),
                "duty_pct": round(e_state.duty_pct, 2),
                "expected_duty_pct": round(expected_duty, 2),
            }
        )
        t += dt_min

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    cargo_temps = [r["t_rear_door"] for r in rows]
    min_temp = min(cargo_temps)
    max_temp = max(cargo_temps)
    minutes_outside_band = sum(
        1 for r in rows if not (spec.min_c <= r["t_rear_door"] <= spec.max_c)
    ) * dt_min

    compressor_cycles = sum(
        1
        for prev, cur in zip(rows, rows[1:], strict=False)
        if (not prev["compressor_on"]) and cur["compressor_on"]
    )

    compressor_currents = [r["i_compressor"] for r in rows]
    mean_compressor_current = sum(compressor_currents) / len(compressor_currents)
    max_compressor_current = max(compressor_currents)
    inrush_events = sum(
        1
        for prev, cur in zip(rows, rows[1:], strict=False)
        if (not prev["compressor_on"]) and cur["compressor_on"]
    )
    min_bus_voltage = min(r["v_bus"] for r in rows)
    mean_duty_pct = sum(r["duty_pct"] for r in rows) / len(rows)
    mean_duty_deviation = sum(r["duty_pct"] - r["expected_duty_pct"] for r in rows) / len(rows)

    ambient_peak_row = max(rows, key=lambda r: r["ambient_c"])
    cargo_peak_row = max(rows, key=lambda r: r["t_rear_door"])

    # This route runs south into rising heat for its whole ~7.5h duration --
    # shorter than a full 24h diurnal cycle -- so raw ambient may never
    # actually turn over and come back down before the journey ends. If its
    # peak sample is the very last row, it was still rising at the end, not
    # a real interior maximum.
    ambient_turned_over = ambient_peak_row["t_min"] < rows[-1]["t_min"]

    summary = {
        "min_cargo_c": min_temp,
        "max_cargo_c": max_temp,
        "minutes_outside_band": minutes_outside_band,
        "compressor_cycles": compressor_cycles,
        "total_km": round(route.total_km, 1),
        "duration_min": round(route.duration_min, 1),
        "ambient_peak_t_min": ambient_peak_row["t_min"],
        "cargo_peak_t_min": cargo_peak_row["t_min"],
        "ambient_turned_over": ambient_turned_over,
        "mean_compressor_current": mean_compressor_current,
        "max_compressor_current": max_compressor_current,
        "inrush_events": inrush_events,
        "min_bus_voltage": min_bus_voltage,
        "mean_duty_pct": mean_duty_pct,
        "mean_duty_deviation": mean_duty_deviation,
    }
    return summary


def _format_hm(t_min: float) -> str:
    total = int(round(t_min))
    return f"{total // 60}h{total % 60:02d}m"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-door-event",
        action="store_true",
        help="Skip the injected door-open event at the Sfax stop (isolates whether "
        "the sealed-compartment cooling margin alone holds band end to end).",
    )
    args = parser.parse_args()

    summary = run(inject_door_event=not args.no_door_event)
    print(f"wrote {OUT_CSV}")
    print(f"total distance:        {summary['total_km']} km")
    print(f"journey duration:      {_format_hm(summary['duration_min'])}")
    print(f"cargo temp range:      {summary['min_cargo_c']:.2f} .. {summary['max_cargo_c']:.2f} C")
    print(f"minutes outside band:  {summary['minutes_outside_band']:.0f}")
    print(f"compressor cycles:     {summary['compressor_cycles']}")

    print(f"mean compressor current: {summary['mean_compressor_current']:.2f} A")
    print(f"max compressor current:  {summary['max_compressor_current']:.2f} A")
    print(f"inrush events:           {summary['inrush_events']}")
    print(f"min bus voltage:         {summary['min_bus_voltage']:.2f} V")
    print(f"mean duty cycle:         {summary['mean_duty_pct']:.1f} %")
    print(f"mean duty deviation:     {summary['mean_duty_deviation']:+.2f} pp (actual - expected)")

    ambient_peak_hm = _format_hm(summary["ambient_peak_t_min"])
    cargo_peak_hm = _format_hm(summary["cargo_peak_t_min"])
    print(f"ambient peak (along this route, raw air temp):   t={ambient_peak_hm}")
    print(f"cargo peak (along this route, rear_door probe):  t={cargo_peak_hm}")
    if summary["ambient_turned_over"]:
        print("ambient turned over during the run (a real interior maximum).")
    else:
        print(
            "ambient did NOT turn over -- still rising at the end of the run. "
            "This route drives south into increasing heat for its whole "
            f"~{_format_hm(summary['duration_min'])}, shorter than a full diurnal "
            "cycle, so this is a spatial/time-of-day trend, not a clean thermal-lag "
            "demonstration. See tests/test_physics.py::"
            "test_cargo_daily_peak_lags_ambient_daily_peak for that isolated case "
            "(vehicle parked at one waypoint for 24h, cooling off, no door events)."
        )


if __name__ == "__main__":
    main()
