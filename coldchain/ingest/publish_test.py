from __future__ import annotations

import os
import time
from datetime import timedelta

import paho.mqtt.publish as mqtt_publish

from ingest.store import Store
from shared.schema import TELEMETRY_TOPIC, TelemetryPacket, example_packet, topic_for
from shared.wire import to_wire

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
# "+" (the service's own default) is a subscribe-only wildcard and cannot be
# published to, so this defaults to a concrete tenant instead. The service's
# default tenant subscription is "+", which matches any concrete tenant here.
TENANT = os.environ.get("TENANT", "demo")
DB_PATH = os.environ.get("DB_PATH", "coldchain.db")

GAP_AFTER_INDEX = 29
GAP_MINUTES = 25
BUFFERED_RANGE = range(29, 34)
UNIQUE_COUNT = 57
DUPLICATE_INDICES = (5, 20, 40)


def build_published_packets() -> list[TelemetryPacket]:
    """57 unique packets (60s apart, with a 25-minute dead zone) + 3 resends."""
    base = example_packet()
    unique: list[TelemetryPacket] = []
    seq = 0
    ts = base.ts
    for i in range(UNIQUE_COUNT):
        if i == GAP_AFTER_INDEX:
            ts += timedelta(minutes=GAP_MINUTES)
        buffered = i in BUFFERED_RANGE
        unique.append(base.model_copy(update={"seq": seq, "ts": ts, "buffered": buffered}))
        seq += 1
        ts += timedelta(seconds=60)

    duplicates = [unique[i] for i in DUPLICATE_INDICES]
    return unique + duplicates


def main() -> None:
    packets = build_published_packets()
    device_id = packets[0].device_id
    topic = topic_for(TELEMETRY_TOPIC, tenant=TENANT, device_id=device_id)
    sent_unique_seqs = {p.seq for p in packets[:UNIQUE_COUNT]}

    print(f"publishing {len(packets)} packets ({UNIQUE_COUNT} unique + "
          f"{len(packets) - UNIQUE_COUNT} duplicates) to {MQTT_HOST}:{MQTT_PORT}")
    print(f"topic: {topic}")

    messages = [{"topic": topic, "payload": to_wire(p), "qos": 1} for p in packets]
    mqtt_publish.multiple(messages, hostname=MQTT_HOST, port=MQTT_PORT)
    print("publish complete; waiting for a separately running ingest.service to catch up...")

    store = Store.open(DB_PATH)
    deadline = time.monotonic() + 15
    matched: list[TelemetryPacket] = []
    last_count = -1
    while time.monotonic() < deadline:
        stored = store.packets(device_id)
        matched = [p for p in stored if p.seq in sent_unique_seqs]
        if len(matched) != last_count:
            print(f"  ...{len(matched)}/{len(sent_unique_seqs)} unique packets stored so far")
            last_count = len(matched)
        if len(matched) >= len(sent_unique_seqs):
            break
        time.sleep(0.5)

    buffered_stored = sum(1 for p in matched if p.buffered)
    gaps = store.gaps(device_id, expected_interval_s=60)

    print("--- derived from the store ingest.service is writing to ---")
    print(f"packets_ok (unique, stored):       {len(matched)} / {len(sent_unique_seqs)}")
    print(f"packets_duplicate (deduped away):  {len(packets) - len(sent_unique_seqs)}")
    print(f"packets_buffered:                  {buffered_stored}")
    print(f"gaps: {gaps}")


if __name__ == "__main__":
    main()
