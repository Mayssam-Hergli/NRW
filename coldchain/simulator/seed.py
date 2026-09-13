"""python -m simulator.seed [--backend sqlite|supabase] [--locale fr|en]

Runs all six scenarios end to end through fusion (models/fusion.py) and the
alert engine (models/alert_engine.py), writes the resulting packets and
alerts into the store, and generates a compliance certificate PDF for each
completed shipment -- so a demo starts from a fleet with real-looking
history instead of an empty dashboard the moment someone scans the QR code.

Each scenario keeps the device_id / shipment_id scheme already used by
simulator/publish.py (TN-{scenario}-GW / SHIP-{scenario}-DEMO), so the two
never collide with each other or with a live publish run into the same
store.

Timestamps are backdated by a whole number of days per scenario (see
_BACKDATE_DAYS) so the six shipments read as a fleet with roughly two weeks
of history rather than six things that all happened in the same hour. A
whole-day shift preserves each packet's hour-of-day exactly, which matters
because models/m1_thermal.py's own ambient estimate is a function of hour
of day -- shifting by anything else would quietly change the fault-timing
behaviour under test elsewhere in this project.
"""

from __future__ import annotations

import argparse
import os
from collections import Counter, deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ingest.service import build_store
from models.alert_engine import AlertEngine
from models.electrical_health import ElectricalHealthMonitor
from models.fusion import fuse
from models.m1_thermal import M1ThermalForecast
from reports.certificate import build_certificate, compute_summary, gather_shipment_data
from reports.templates import CERT_LOCALES
from shared.schema import TelemetryPacket
from simulator.electrical import ElectricalSim
from simulator.scenarios import SCENARIOS

OUT_DIR = Path(__file__).parent.parent / "reports" / "out"
HISTORY_LIMIT = 30

# Kept well short of these scenarios' multi-day/multi-hour full runs so
# seeding finishes in seconds -- both are only interesting for their first
# stretch of behaviour anyway. Same durations tests/test_alert_engine_report.py
# uses, for the same reason.
_DURATION_MIN: dict[str, float] = {
    "refrigerant_loss": 6000.0,
    "compressor_failure": 260.0,
}

# Three days apart, most recent last -- a fleet with history, not a demo
# that happened all in one hour.
_BACKDATE_DAYS: dict[str, int] = {
    "nominal": 13,
    "door_open": 10,
    "refrigerant_loss": 8,
    "compressor_failure": 6,
    "freeze_risk": 3,
    "dead_zone": 1,
}


def _device_id(name: str) -> str:
    return f"TN-{name}-GW"


def _shift_packet(packet: TelemetryPacket, delta: timedelta) -> TelemetryPacket:
    return packet.model_copy(update={"ts": packet.ts + delta})


def _run_scenario_into_store(name: str, cls, store, *, now: datetime) -> dict:
    device_id = _device_id(name)
    scenario = cls(device_id=device_id)
    duration = _DURATION_MIN.get(name)

    packets = list(scenario.run(duration_min=duration, dt_s=60.0))
    delta = (now - timedelta(days=_BACKDATE_DAYS[name])) - packets[0].ts
    packets = [_shift_packet(p, delta) for p in packets]

    m1 = M1ThermalForecast()
    m2 = ElectricalHealthMonitor(dt_min=1.0)
    elec = ElectricalSim(scenario.profile)
    engine = AlertEngine()
    history: deque[TelemetryPacket] = deque(maxlen=HISTORY_LIMIT)

    seen_alert_ids: set[str] = set()
    causes: Counter[str] = Counter()

    for packet in packets:
        store.insert_packet(packet)

        r1 = m1.update(packet)
        expected_duty = elec.expected_duty_pct(packet.ambient_c, packet.gnss.speed_kmh)
        r2 = m2.update(packet, expected_duty)
        diagnosis = fuse(packet, r1, r2, None, list(history))

        for record in engine.update(packet, diagnosis):
            if record.alert_id in seen_alert_ids:
                store.update_alert(record)
            else:
                store.insert_alert(record)
                seen_alert_ids.add(record.alert_id)
            causes[record.cause.value] += 1
        history.append(packet)

    return {
        "scenario": name,
        "shipment_id": scenario.shipment_id,
        "device_id": device_id,
        "packet_count": len(packets),
        "alert_count": len(seen_alert_ids),
        "causes": causes,
    }


def seed(
    store,
    *,
    locale: str = "fr",
    out_dir: Path = OUT_DIR,
    now: datetime | None = None,
) -> list[dict]:
    """Seed all six scenarios into `store` and write a certificate PDF for
    each. Returns one result dict per scenario (scenario, shipment_id,
    device_id, packet_count, alert_count, verdict, certificate_path)."""
    now = now or datetime.now(UTC)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for name, cls in SCENARIOS.items():
        result = _run_scenario_into_store(name, cls, store, now=now)

        record = gather_shipment_data(result["shipment_id"], store)
        summary = compute_summary(record.packets, record.profile)
        pdf_bytes = build_certificate(result["shipment_id"], store, locale=locale)
        cert_path = out_dir / f"{result['shipment_id']}_{locale}.pdf"
        cert_path.write_bytes(pdf_bytes)

        result["verdict"] = summary.budget.verdict
        result["certificate_path"] = cert_path
        results.append(result)
    return results


def _print_summary(results: list[dict]) -> None:
    print()
    print(f"{'scenario':<20} {'shipment_id':<24} {'packets':>7} {'alerts':>7}  verdict")
    print("-" * 90)
    for r in results:
        print(
            f"{r['scenario']:<20} {r['shipment_id']:<24} {r['packet_count']:>7} "
            f"{r['alert_count']:>7}  {r['verdict'].value}"
        )
    print()
    print(f"wrote {len(results)} shipments and certificates")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("sqlite", "supabase"), default=None)
    parser.add_argument("--locale", choices=CERT_LOCALES, default="fr")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    if args.backend is not None:
        os.environ["STORE_BACKEND"] = args.backend

    store = build_store()
    print(f"seeding into backend={os.environ.get('STORE_BACKEND', 'sqlite')}")
    results = seed(store, locale=args.locale, out_dir=args.out_dir)
    _print_summary(results)


if __name__ == "__main__":
    main()
