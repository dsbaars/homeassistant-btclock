"""Button entities: identify, restart, full refresh, screen nav, frontlight flash.

Some buttons are available on both firmware variants (identify, restart,
full_refresh — exposed as GET on legacy, POST on 3.4+). Others are 3.4.0+
only (screen_next/previous, frontlight_flash). Each description declares
the path-table key it drives, and we filter setup by asking the current
variant's path table whether the key exists.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BtclockConfigEntry
from .api_paths import PATHS
from .coordinator import BtclockCoordinator
from .entity import BtclockEntity


@dataclass(frozen=True, kw_only=True)
class BtclockButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[BtclockCoordinator], Awaitable[None]]
    path_key: str
    available_fn: Callable[[BtclockCoordinator], bool] | None = None


BUTTONS: tuple[BtclockButtonDescription, ...] = (
    BtclockButtonDescription(
        key="identify",
        translation_key="identify",
        device_class=ButtonDeviceClass.IDENTIFY,
        entity_category=EntityCategory.DIAGNOSTIC,
        press_fn=lambda c: c.client.async_identify(),
        path_key="identify",
    ),
    BtclockButtonDescription(
        key="restart",
        translation_key="restart",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.client.async_restart(),
        path_key="restart",
    ),
    BtclockButtonDescription(
        key="full_refresh",
        translation_key="full_refresh",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.client.async_full_refresh(),
        path_key="full_refresh",
    ),
    BtclockButtonDescription(
        key="screen_next",
        translation_key="screen_next",
        press_fn=lambda c: c.client.async_screen_next(),
        path_key="screen_next",
    ),
    BtclockButtonDescription(
        key="screen_previous",
        translation_key="screen_previous",
        press_fn=lambda c: c.client.async_screen_previous(),
        path_key="screen_prev",
    ),
    BtclockButtonDescription(
        key="frontlight_flash",
        translation_key="frontlight_flash",
        press_fn=lambda c: c.client.async_frontlight_flash(),
        path_key="frontlight_flash",
        available_fn=lambda c: bool(c.client.settings.get("hasFrontlight")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BtclockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    variant_paths = PATHS[coordinator.client.variant]
    async_add_entities(
        BtclockButton(coordinator, desc)
        for desc in BUTTONS
        if desc.path_key in variant_paths
        and (desc.available_fn is None or desc.available_fn(coordinator))
    )


class BtclockButton(BtclockEntity, ButtonEntity):
    entity_description: BtclockButtonDescription

    def __init__(
        self,
        coordinator: BtclockCoordinator,
        description: BtclockButtonDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.coordinator)
        await self.coordinator.async_request_refresh()
