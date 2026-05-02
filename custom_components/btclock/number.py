"""Number entities: LED brightness (and any future settings-backed sliders)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfTime
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
    available_fn: Callable[[BtclockCoordinator], bool] | None = None


def _setting_present(key: str) -> Callable[[BtclockCoordinator], bool]:
    def _check(c: BtclockCoordinator) -> bool:
        return c.client.settings.get(key) is not None

    return _check


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
    # v4-only poll cadences. Bounds mirror the firmware's schema so the
    # device can't reject a value the slider produced.
    BtclockSettingsNumberDescription(
        key="bitaxe_poll_sec",
        translation_key="bitaxe_poll_sec",
        icon="mdi:timer-cog-outline",
        native_min_value=5,
        native_max_value=300,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        setting_key="bitaxePollSec",
        available_fn=_setting_present("bitaxePollSec"),
    ),
    BtclockSettingsNumberDescription(
        key="pool_poll_sec",
        translation_key="pool_poll_sec",
        icon="mdi:timer-cog-outline",
        native_min_value=10,
        native_max_value=3600,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        setting_key="poolPollSec",
        available_fn=_setting_present("poolPollSec"),
    ),
    BtclockSettingsNumberDescription(
        key="full_refresh_min",
        translation_key="full_refresh_min",
        icon="mdi:refresh",
        native_min_value=0,
        native_max_value=24 * 60,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        setting_key="fullRefreshMin",
        available_fn=_setting_present("fullRefreshMin"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BtclockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        BtclockSettingsNumber(coordinator, desc)
        for desc in SETTINGS_NUMBERS
        if desc.available_fn is None or desc.available_fn(coordinator)
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
