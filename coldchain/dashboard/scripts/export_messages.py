"""Generates dashboard/src/generated/messages.json from shared/messages.py.

shared/messages.py is the one source of truth for every user-facing string
in this project (firmware, dashboard, reports all read from it). This
script is the only place that duplicates its *data* into another language
-- everything else in dashboard/ imports the JSON this produces, never a
hand-copied string. Run via `npm run gen:messages` (wired as a prebuild
step) or directly: `python scripts/export_messages.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_COLDCHAIN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_COLDCHAIN_ROOT))

from shared.enums import FaultCause, Severity  # noqa: E402
from shared.messages import (  # noqa: E402
    AUDIENCES,
    BANNED_DRIVER_JARGON,
    CAUSE_COPY,
    COUNTDOWN_CLAUSE,
    DEFAULT_LOCALE,
    DRIVER_MAX_CHARS,
    LOCALES,
    SAFE_NOW_CLAUSE,
    SEVERITY_LABEL,
)

OUT_PATH = Path(__file__).resolve().parent.parent / "src" / "generated" / "messages.json"


def build() -> dict[str, object]:
    return {
        "locales": list(LOCALES),
        "defaultLocale": DEFAULT_LOCALE,
        "audiences": list(AUDIENCES),
        "driverMaxChars": DRIVER_MAX_CHARS,
        "bannedDriverJargon": list(BANNED_DRIVER_JARGON),
        "severityLabel": {
            severity.value: labels for severity, labels in SEVERITY_LABEL.items()
        },
        "safeNowClause": dict(SAFE_NOW_CLAUSE),
        "countdownClause": dict(COUNTDOWN_CLAUSE),
        "causeCopy": {
            cause.value: {
                audience: dict(locale_map) for audience, locale_map in by_audience.items()
            }
            for cause, by_audience in CAUSE_COPY.items()
        },
        # Exported for the frontend's own completeness checks, so the TS
        # side never has to hardcode "there are 15 causes" independently.
        "allCauses": [c.value for c in FaultCause],
        "allSeverities": [s.value for s in Severity],
    }


def main() -> None:
    data = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
