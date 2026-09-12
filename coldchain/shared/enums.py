from __future__ import annotations

from enum import StrEnum


class MissionProfile(StrEnum):
    pharma_refrigerated = "pharma_refrigerated"
    pharma_frozen = "pharma_frozen"
    controlled_room_temp = "controlled_room_temp"
    vaccines = "vaccines"
    fresh_produce = "fresh_produce"


class CompressorState(StrEnum):
    RUN = "RUN"
    OFF = "OFF"
    SHORT_CYCLE = "SHORT_CYCLE"
    FAULT = "FAULT"


class GnssFix(StrEnum):
    NONE = "NONE"
    D2 = "2D"
    D3 = "3D"


class ProbePosition(StrEnum):
    front = "front"
    rear_door = "rear_door"
    top = "top"
    bottom = "bottom"
    ambient_external = "ambient_external"


class AlertState(StrEnum):
    nominal = "nominal"
    suppressed = "suppressed"
    watch = "watch"
    warning = "warning"
    critical = "critical"
    escalated = "escalated"
    acknowledged = "acknowledged"
    resolved = "resolved"


class Severity(StrEnum):
    watch = "watch"
    warning = "warning"
    critical = "critical"


class FaultCause(StrEnum):
    bearing_wear = "bearing_wear"
    refrigerant_loss = "refrigerant_loss"
    short_cycling = "short_cycling"
    fan_failure = "fan_failure"
    voltage_sag = "voltage_sag"
    unit_off = "unit_off"
    offload_stop = "offload_stop"
    door_unsecured = "door_unsecured"
    seal_failure = "seal_failure"
    freeze_risk = "freeze_risk"
    shock_impact = "shock_impact"
    light_exposure = "light_exposure"
    tag_lost = "tag_lost"
    ambient_strain = "ambient_strain"
    device_degraded = "device_degraded"


class PrescribedAction(StrEnum):
    close_door = "close_door"
    secure_door = "secure_door"
    restart_unit = "restart_unit"
    check_electrical = "check_electrical"
    inspect_fan = "inspect_fan"
    inspect_seals = "inspect_seals"
    reposition_pallets = "reposition_pallets"
    precool_now = "precool_now"
    raise_within_band = "raise_within_band"
    divert_cold_store = "divert_cold_store"
    call_dispatch = "call_dispatch"
    schedule_service = "schedule_service"
    pull_over_then_check = "pull_over_then_check"
    service_device = "service_device"


class DriverCause(StrEnum):
    offload_stop = "offload_stop"
    door_left_open = "door_left_open"
    unit_failure = "unit_failure"
    power_issue = "power_issue"
    loading_delay = "loading_delay"
    other = "other"


class Outcome(StrEnum):
    pending = "pending"
    recovered = "recovered"
    not_recovered = "not_recovered"


class Scenario(StrEnum):
    nominal = "nominal"
    door_open = "door_open"
    refrigerant_loss = "refrigerant_loss"
    compressor_failure = "compressor_failure"
    freeze_risk = "freeze_risk"
    dead_zone = "dead_zone"
