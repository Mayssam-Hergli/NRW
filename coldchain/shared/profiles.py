from __future__ import annotations

from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, model_validator

from shared.enums import MissionProfile


class ProfileSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    min_c: float
    max_c: float
    freeze_alarm: bool
    cumulative_excursion_limit_min: int
    max_lux_hours: float | None
    max_shock_g: float
    door_dwell_limit_min: int

    @model_validator(mode="after")
    def _check_band(self) -> ProfileSpec:
        if self.min_c >= self.max_c:
            raise ValueError("min_c must be less than max_c")
        return self


_PROFILES: dict[MissionProfile, ProfileSpec] = {
    MissionProfile.pharma_refrigerated: ProfileSpec(
        label="Pharma Refrigerated",
        min_c=2.0,
        max_c=8.0,
        freeze_alarm=False,
        cumulative_excursion_limit_min=30,
        max_lux_hours=None,
        max_shock_g=6.0,
        door_dwell_limit_min=10,
    ),
    MissionProfile.pharma_frozen: ProfileSpec(
        label="Pharma Frozen",
        min_c=-25.0,
        max_c=-15.0,
        freeze_alarm=False,
        cumulative_excursion_limit_min=10,
        max_lux_hours=None,
        max_shock_g=6.0,
        door_dwell_limit_min=5,
    ),
    MissionProfile.controlled_room_temp: ProfileSpec(
        label="Controlled Room Temperature",
        min_c=15.0,
        max_c=25.0,
        freeze_alarm=False,
        cumulative_excursion_limit_min=120,
        max_lux_hours=None,
        max_shock_g=8.0,
        door_dwell_limit_min=20,
    ),
    # Vaccines get a freeze alarm even though the band's lower bound (2C) is
    # well above 0C: most vaccine cold-chain excursions are freeze events,
    # not heat events, and systems that only watch the upper bound miss them.
    MissionProfile.vaccines: ProfileSpec(
        label="Vaccines",
        min_c=2.0,
        max_c=8.0,
        freeze_alarm=True,
        cumulative_excursion_limit_min=15,
        max_lux_hours=250.0,
        max_shock_g=4.0,
        door_dwell_limit_min=8,
    ),
    MissionProfile.fresh_produce: ProfileSpec(
        label="Fresh Produce",
        min_c=0.0,
        max_c=4.0,
        freeze_alarm=True,
        cumulative_excursion_limit_min=60,
        max_lux_hours=None,
        max_shock_g=10.0,
        door_dwell_limit_min=15,
    ),
}

PROFILES = MappingProxyType(_PROFILES)


def get_profile(profile: MissionProfile) -> ProfileSpec:
    return PROFILES[profile]
