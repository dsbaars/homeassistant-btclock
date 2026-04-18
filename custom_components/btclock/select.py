"""Select entities: screen + currency."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    entities: list[SelectEntity] = [BtclockScreenSelect(coordinator)]
    if (
        coordinator.client.variant is ApiVariant.V3_4
        and coordinator.client.settings.get("actCurrencies")
    ):
        entities.append(BtclockCurrencySelect(coordinator))
    async_add_entities(entities)


class BtclockScreenSelect(BtclockEntity, SelectEntity):
    _attr_translation_key = "screen"
    _attr_icon = "mdi:monitor"

    def __init__(self, coordinator: BtclockCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_screen"

    def _screens(self) -> list[dict]:
        """All screens, enabled or not.

        The firmware lets a client switch to any screen via
        POST /api/show/screen regardless of its `enabled` flag — that only
        controls whether the screen appears in auto-rotation
        (src/lib/ui/screen_handler.cpp:148). So we expose the full list.
        """
        return list(self.coordinator.client.settings.get("screens") or [])

    @property
    def options(self) -> list[str]:
        return [s.get("name", "") for s in self._screens()]

    @property
    def current_option(self) -> str | None:
        current_id = self.coordinator.data.get("currentScreen")
        for s in self._screens():
            if s.get("id") == current_id:
                return s.get("name")
        return None

    async def async_select_option(self, option: str) -> None:
        for s in self._screens():
            if s.get("name") == option:
                screen_id = int(s["id"])
                await self.coordinator.client.async_set_screen(screen_id)
                self.coordinator.async_apply_optimistic({"currentScreen": screen_id})
                return


class BtclockCurrencySelect(BtclockEntity, SelectEntity):
    _attr_translation_key = "currency"
    _attr_icon = "mdi:currency-usd"

    def __init__(self, coordinator: BtclockCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_currency"

    @property
    def options(self) -> list[str]:
        return list(self.coordinator.client.settings.get("actCurrencies") or [])

    @property
    def current_option(self) -> str | None:
        return self.coordinator.data.get("currency")

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.client.async_set_currency(option)
        self.coordinator.async_apply_optimistic({"currency": option})
