from __future__ import annotations

from ingest.store import Store
from simulator.publish import default_device_id
from simulator.scenarios import SCENARIOS

SHORT_DURATION_MIN = 45.0


def test_default_device_id_is_unique_per_scenario() -> None:
    ids = {name: default_device_id(name) for name in SCENARIOS}
    assert len(set(ids.values())) == len(ids)
    for name, device_id in ids.items():
        assert device_id == f"TN-{name}-GW"


def test_two_scenarios_published_into_one_store_both_persist_fully(tmp_path) -> None:
    """Regression test for the (device_id, seq) collision: every scenario's
    packets start at seq 0, so publishing two scenarios under the same
    device id would silently dedup the second one away. With each scenario
    defaulting to its own device id, both should persist in full.
    """
    store = Store.open(tmp_path / "test.db")

    persisted: dict[str, tuple[str, int]] = {}
    for name in ("nominal", "door_open"):
        device_id = default_device_id(name)
        scenario = SCENARIOS[name](device_id=device_id)
        packets = list(scenario.run(duration_min=SHORT_DURATION_MIN, dt_s=60.0))
        for packet in packets:
            assert store.insert_packet(packet) is True, (
                f"{name}: packet seq={packet.seq} was rejected as a duplicate"
            )
        persisted[name] = (device_id, len(packets))

    for name, (device_id, expected_count) in persisted.items():
        stored = store.packets(device_id)
        assert len(stored) == expected_count, name
        assert [p.seq for p in stored] == list(range(expected_count)), name
