"""Switch entities: screen timer + DND (3.4.0)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BtclockConfigEntry
from .coordinator import BtclockCoordinator
from .entity import BtclockEntity
from .models import ApiVariant


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BtclockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [BtclockTimerSwitch(coordinator)]
    if coordinator.client.variant is ApiVariant.V3_4:
        entities.append(BtclockDndSwitch(coordinator))
    async_add_entities(entities)


class BtclockTimerSwitch(BtclockEntity, SwitchEntity):
    _attr_translation_key = "timer"
    _attr_icon = "mdi:monitor-shimmer"

    def __init__(self, coordinator: BtclockCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_timer"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("timerRunning")

    async def async_turn_on(self, **_: Any) -> None:
        await self.coordinator.client.async_timer_start()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **_: Any) -> None:
        await self.coordinator.client.async_timer_stop()
        await self.coordinator.async_request_refresh()


class BtclockDndSwitch(BtclockEntity, SwitchEntity):
    _attr_translation_key = "dnd"
    _attr_icon = "mdi:minus-circle-off"

    def __init__(self, coordinator: BtclockCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_dnd"

    @property
    def is_on(self) -> bool | None:
        dnd = self.coordinator.data.get("dnd") or {}
        return dnd.get("enabled")

    async def async_turn_on(self, **_: Any) -> None:
        await self.coordinator.client.async_dnd_enable()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **_: Any) -> None:
        await self.coordinator.client.async_dnd_disable()
        await self.coordinator.async_request_refresh()
