"""Publishes a scenario's packets to MQTT the way the real gateway would:
CBOR over shared.wire.to_wire (never JSON -- that's the production path),
at a configurable speed-up over the simulated clock.

    python -m simulator.publish --scenario door_open --speed 60x \\
        --device TN-1234-GW --tenant nrw8-xxxx --broker $MQTT_HOST

For dead_zone, packets the scenario has already marked buffered=True (the
outage window) are held back instead of published in real time, then sent
in a burst -- still carrying their original timestamps -- the instant a
live (non-buffered) packet resumes, exactly like a gateway replaying its
flash buffer after reconnecting.
"""

from __future__ import annotations

import argparse
import os
import time
from collections import deque

import paho.mqtt.client as mqtt

from shared.schema import TELEMETRY_TOPIC, TelemetryPacket, topic_for
from shared.wire import to_wire
from simulator.scenarios import SCENARIOS

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
# "+" (ingest.service's own default) is a subscribe-only wildcard and can't
# be published to, so this defaults to a concrete tenant instead, matching
# ingest/publish_test.py's precedent.
TENANT = os.environ.get("TENANT", "demo")
DEFAULT_DEVICE_ID = "TN-1234-GW"


def _parse_speed(text: str) -> float:
    value = float(text.strip().lower().rstrip("x"))
    if value <= 0:
        raise ValueError(f"speed must be positive, got {text!r}")
    return value


class _Publisher:
    """Thin wrapper around a persistent paho client, tracking connection
    state for the live status line. Uses connect_async + loop_start +
    reconnect_delay_set (same pattern as ingest.service) so an unreachable
    broker at startup doesn't crash the demo -- it just shows "retrying".
    """

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.state = "connecting"
        self._client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_connect_fail = self._on_connect_fail
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        self.state = "connected"

    def _on_disconnect(
        self, client, userdata, disconnect_flags, reason_code, properties=None
    ) -> None:
        self.state = "disconnected"

    def _on_connect_fail(self, client, userdata) -> None:
        self.state = "retrying"

    def start(self) -> None:
        self._client.connect_async(self.host, self.port)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def publish(self, topic: str, payload: bytes) -> None:
        self._client.publish(topic, payload, qos=1)


def _status_line(scenario_name: str, packet: TelemetryPacket, elapsed_s: float, state: str) -> str:
    worst_c = max(c.t_c for c in packet.cargo)
    duty = packet.power.compressor.duty_pct or 0.0
    return (
        f"\r[{scenario_name}] sim={packet.ts.strftime('%Y-%m-%d %H:%M:%S')} "
        f"elapsed={elapsed_s:7.1f}s cargo={worst_c:6.2f}C duty={duty:5.1f}% "
        f"conn={state:<11}"
    )


def run_publisher(
    scenario_name: str,
    *,
    speed: float,
    device_id: str,
    tenant: str,
    host: str,
    port: int,
    duration_min: float | None,
    dt_s: float,
) -> None:
    scenario = SCENARIOS[scenario_name](device_id=device_id)
    topic = topic_for(TELEMETRY_TOPIC, tenant=tenant, device_id=device_id)

    publisher = _Publisher(host, port)
    publisher.start()
    start_time = time.monotonic()
    pending: deque[TelemetryPacket] = deque()

    try:
        for packet in scenario.run(duration_min=duration_min, dt_s=dt_s):
            if packet.buffered:
                pending.append(packet)
            else:
                while pending:
                    publisher.publish(topic, to_wire(pending.popleft()))
                publisher.publish(topic, to_wire(packet))

            elapsed_s = time.monotonic() - start_time
            line = _status_line(scenario_name, packet, elapsed_s, publisher.state)
            print(line, end="", flush=True)
            time.sleep(dt_s / speed)

        while pending:
            publisher.publish(topic, to_wire(pending.popleft()))
    finally:
        print()
        publisher.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    parser.add_argument("--speed", default="1x", help='Time compression, e.g. "60x".')
    parser.add_argument("--device", dest="device_id", default=DEFAULT_DEVICE_ID)
    parser.add_argument("--tenant", default=TENANT)
    parser.add_argument("--broker", dest="host", default=MQTT_HOST)
    parser.add_argument("--port", type=int, default=MQTT_PORT)
    parser.add_argument("--duration-min", type=float, default=None)
    parser.add_argument("--dt-s", type=float, default=60.0)
    args = parser.parse_args()

    try:
        run_publisher(
            args.scenario,
            speed=_parse_speed(args.speed),
            device_id=args.device_id,
            tenant=args.tenant,
            host=args.host,
            port=args.port,
            duration_min=args.duration_min,
            dt_s=args.dt_s,
        )
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
