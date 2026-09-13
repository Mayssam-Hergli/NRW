"""Role and locale selection for the dashboard (step 11).

No accounts, no passwords -- this only needs to exist so the dashboard has
a fixed enum and locale list to build a selector against.
"""

from __future__ import annotations

from enum import StrEnum

from shared.messages import DEFAULT_LOCALE, LOCALES

__all__ = ["DEFAULT_LOCALE", "LOCALES", "Role"]


class Role(StrEnum):
    driver = "driver"
    dispatcher = "dispatcher"
    quality = "quality"
