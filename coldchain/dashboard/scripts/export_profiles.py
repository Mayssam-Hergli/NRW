"""Generates dashboard/src/generated/profiles.json from shared/profiles.py.

Same reasoning as export_messages.py: shared/profiles.py's PROFILES table
is real data (band edges, freeze_alarm, excursion limits) that M3's
verdict logic depends on -- the TS side must not hand-copy it and risk
silent drift, it imports this generated file instead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_COLDCHAIN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_COLDCHAIN_ROOT))

from shared.profiles import PROFILES  # noqa: E402

OUT_PATH = Path(__file__).resolve().parent.parent / "src" / "generated" / "profiles.json"


def build() -> dict[str, object]:
    return {
        profile.value: {
            "label": spec.label,
            "minC": spec.min_c,
            "maxC": spec.max_c,
            "freezeAlarm": spec.freeze_alarm,
            "cumulativeExcursionLimitMin": spec.cumulative_excursion_limit_min,
            "maxLuxHours": spec.max_lux_hours,
            "maxShockG": spec.max_shock_g,
            "doorDwellLimitMin": spec.door_dwell_limit_min,
        }
        for profile, spec in PROFILES.items()
    }


def main() -> None:
    data = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
