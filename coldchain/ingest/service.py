from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from dataclasses import dataclass

import paho.mqtt.client as mqtt

from ingest.store import Store
from ingest.supabase_store import SupabaseStore
from shared.schema import ALERT_TOPIC, TELEMETRY_TOPIC, AlertRecord, TelemetryPacket, topic_for
from shared.wire import from_wire

logger = logging.getLogger("ingest.service")

AnyStore = Store | SupabaseStore


def build_store() -> AnyStore:
    """Pick the persistence backend from STORE_BACKEND ("sqlite", the
    default, or "supabase"). Both backends expose the same instance
    interface, so nothing downstream of this needs to know which one it
    got.
    """
    backend = os.environ.get("STORE_BACKEND", "sqlite").lower()
    if backend == "supabase":
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        return SupabaseStore.open(url, key)
    if backend == "sqlite":
        db_path = os.environ.get("DB_PATH", "coldchain.db")
        return Store.open(db_path)
    raise ValueError(f"unknown STORE_BACKEND: {backend!r} (expected 'sqlite' or 'supabase')")


@dataclass
class Counters:
    packets_ok: int = 0
    packets_invalid: int = 0
    packets_duplicate: int = 0
    packets_buffered: int = 0
    alerts_ok: int = 0


def decode_telemetry(payload: bytes) -> tuple[TelemetryPacket, str]:
    """Try CBOR wire format first, fall back to readable JSON."""
    try:
        return from_wire(payload), "cbor"
    except Exception:
        pass
    return TelemetryPacket.model_validate_json(payload), "json"


def decode_alert(payload: bytes) -> AlertRecord:
    return AlertRecord.model_validate_json(payload)


class IngestService:
    def __init__(self, store: AnyStore, host: str, port: int, tenant: str) -> None:
        self.store = store
        self.host = host
        self.port = port
        self.tenant = tenant
        self.counters = Counters()
        self._queue: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = asyncio.Event()
        self._client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_connect_fail = self._on_connect_fail
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: object,
        reason_code: object,
        properties: object = None,
    ) -> None:
        telemetry_topic = topic_for(TELEMETRY_TOPIC, tenant=self.tenant, device_id="+")
        alert_topic = topic_for(ALERT_TOPIC, tenant=self.tenant, device_id="+")
        client.subscribe(telemetry_topic)
        client.subscribe(alert_topic)
        logger.info("connected, subscribed to %s and %s", telemetry_topic, alert_topic)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: object,
        disconnect_flags: object,
        reason_code: object,
        properties: object = None,
    ) -> None:
        if not self._stop_event.is_set():
            logger.warning(
                "disconnected from broker (reason_code=%s); reconnecting with backoff",
                reason_code,
            )

    def _on_connect_fail(self, client: mqtt.Client, userdata: object) -> None:
        logger.warning(
            "connection attempt to %s:%s failed; retrying with backoff", self.host, self.port
        )

    def _on_message(self, client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, (msg.topic, msg.payload))

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        # connect_async + loop_start hands the connection (and all retries) to
        # paho's network thread, so an unreachable broker at startup logs a
        # warning via on_connect_fail instead of raising ConnectionRefusedError
        # here. reconnect_delay_set above makes it retry with backoff, and the
        # same machinery reconnects automatically if the broker drops mid-run.
        self._client.connect_async(self.host, self.port)
        self._client.loop_start()
        try:
            while not self._stop_event.is_set():
                try:
                    topic, payload = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                except TimeoutError:
                    continue
                await asyncio.to_thread(self._handle_message, topic, payload)
        finally:
            self._client.loop_stop()
            self._client.disconnect()

    def stop(self) -> None:
        self._stop_event.set()

    def _handle_message(self, topic: str, payload: bytes) -> None:
        parts = topic.split("/")
        device_id = parts[3] if len(parts) > 3 else "unknown"
        if topic.endswith("/telemetry"):
            self._handle_telemetry(device_id, payload)
        elif topic.endswith("/alert"):
            self._handle_alert(device_id, payload)

    def _handle_telemetry(self, device_id: str, payload: bytes) -> None:
        try:
            packet, codec = decode_telemetry(payload)
        except Exception as exc:
            logger.error("invalid telemetry payload from %s: %s", device_id, exc)
            self.counters.packets_invalid += 1
            return
        logger.debug("decoded telemetry from %s via %s", packet.device_id, codec)
        if self.store.insert_packet(packet):
            self.counters.packets_ok += 1
            if packet.buffered:
                self.counters.packets_buffered += 1
        else:
            self.counters.packets_duplicate += 1

    def _handle_alert(self, device_id: str, payload: bytes) -> None:
        try:
            alert = decode_alert(payload)
        except Exception as exc:
            logger.error("invalid alert payload from %s: %s", device_id, exc)
            self.counters.packets_invalid += 1
            return
        if not self.store.insert_alert(alert):
            self.store.update_alert(alert)
        self.counters.alerts_ok += 1


async def _run(service: IngestService) -> None:
    def _handle_sigint(signum: int, frame: object) -> None:
        logger.info("SIGINT received, shutting down")
        service.stop()

    with contextlib.suppress(ValueError):
        signal.signal(signal.SIGINT, _handle_sigint)

    await service.run()
    logger.info("counters: %s", service.counters)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    host = os.environ.get("MQTT_HOST", "localhost")
    port = int(os.environ.get("MQTT_PORT", "1883"))
    tenant = os.environ.get("TENANT", "+")

    store = build_store()
    service = IngestService(store, host=host, port=port, tenant=tenant)
    asyncio.run(_run(service))


if __name__ == "__main__":
    main()
