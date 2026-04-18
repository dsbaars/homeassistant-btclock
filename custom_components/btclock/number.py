"""Number entities: LED brightness (and any future settings-backed sliders)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BtclockConfigEntry
from .coordinator import BtclockCoordinator
from .entity import BtclockEntity


@dataclass(frozen=True, kw_only=True)
class BtclockSettingsNumberDescription(NumberEntityDescription):
    """A numeric settings field that writes via PATCH /api/settings."""

    setting_key: str


SETTINGS_NUMBERS: tuple[BtclockSettingsNumberDescription, ...] = (
    BtclockSettingsNumberDescription(
        key="led_brightness",
        translation_key="led_brightness",
        icon="mdi:brightness-6",
        native_min_value=0,
        native_max_value=255,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.SLIDER,
        setting_key="ledBrightness",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BtclockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        BtclockSettingsNumber(coordinator, desc) for desc in SETTINGS_NUMBERS
    )


class BtclockSettingsNumber(BtclockEntity, NumberEntity):
    entity_description: BtclockSettingsNumberDescription

    def __init__(
        self,
        coordinator: BtclockCoordinator,
        description: BtclockSettingsNumberDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        raw = self.coordinator.client.settings.get(self.entity_description.setting_key)
        return float(raw) if raw is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_patch_settings(
            {self.entity_description.setting_key: int(value)}
        )
