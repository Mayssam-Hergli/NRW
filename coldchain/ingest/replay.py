from __future__ import annotations

import argparse
import sys

from ingest.store import Store
from shared.schema import TelemetryPacket


def replay(file_path: str, db_path: str) -> tuple[int, int, int]:
    """Load a JSON-lines capture of TelemetryPackets into a store.

    Returns (inserted, duplicate, invalid) counts.
    """
    store = Store.open(db_path)
    inserted = duplicate = invalid = 0
    with open(file_path, encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                packet = TelemetryPacket.model_validate_json(line)
            except Exception as exc:
                print(f"line {line_no}: invalid packet: {exc}", file=sys.stderr)
                invalid += 1
                continue
            if store.insert_packet(packet):
                inserted += 1
            else:
                duplicate += 1
    return inserted, duplicate, invalid


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay a JSON-lines telemetry capture into a SQLite store."
    )
    parser.add_argument("--file", required=True, help="Path to a JSON-lines capture file.")
    parser.add_argument("--db", required=True, help="Path to the SQLite store.")
    args = parser.parse_args()

    inserted, duplicate, invalid = replay(args.file, args.db)
    print(f"inserted={inserted} duplicate={duplicate} invalid={invalid}")


if __name__ == "__main__":
    main()
