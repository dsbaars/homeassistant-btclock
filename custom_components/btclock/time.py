"""Time entities: DND schedule start/end (firmware 3.4.0+)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BtclockConfigEntry
from .coordinator import BtclockCoordinator
from .entity import BtclockEntity
from .models import ApiVariant
from .switch import merged_dnd_patch


@dataclass(frozen=True, kw_only=True)
class _DndTimeSpec:
    """Maps a HA time entity to a (hourKey, minuteKey) pair on settings.dnd."""

    key: str
    translation_key: str
    icon: str
    hour_key: str
    minute_key: str


_SPECS: tuple[_DndTimeSpec, ...] = (
    _DndTimeSpec(
        key="dnd_start",
        translation_key="dnd_start",
        icon="mdi:clock-start",
        hour_key="startHour",
        minute_key="startMinute",
    ),
    _DndTimeSpec(
        key="dnd_end",
        translation_key="dnd_end",
        icon="mdi:clock-end",
        hour_key="endHour",
        minute_key="endMinute",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BtclockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.client.variant is not ApiVariant.V3_4:
        return
    async_add_entities(BtclockDndTime(coordinator, spec) for spec in _SPECS)


class BtclockDndTime(BtclockEntity, TimeEntity):
    """Start/end of the DND quiet-hours window.

    The firmware's PATCH handler only applies a time-range change when all
    four schedule fields (startHour/Minute, endHour/Minute) are present in
    the `dnd` block, so every write re-sends the other three alongside the
    one the user edited.
    """

    def __init__(self, coordinator: BtclockCoordinator, spec: _DndTimeSpec) -> None:
        super().__init__(coordinator)
        self._spec = spec
        self._attr_translation_key = spec.translation_key
        self._attr_icon = spec.icon
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{spec.key}"

    @property
    def native_value(self) -> time | None:
        cfg = self.coordinator.client.settings.get("dnd") or {}
        h = cfg.get(self._spec.hour_key)
        m = cfg.get(self._spec.minute_key)
        if h is None or m is None:
            return None
        return time(int(h), int(m))

    async def async_set_value(self, value: time) -> None:
        cfg = self.coordinator.client.settings.get("dnd") or {}
        fields = {
            "startHour": int(cfg.get("startHour", 0)),
            "startMinute": int(cfg.get("startMinute", 0)),
            "endHour": int(cfg.get("endHour", 0)),
            "endMinute": int(cfg.get("endMinute", 0)),
            self._spec.hour_key: value.hour,
            self._spec.minute_key: value.minute,
        }
        await self.coordinator.async_patch_settings(
            merged_dnd_patch(self.coordinator, **fields)
        )
