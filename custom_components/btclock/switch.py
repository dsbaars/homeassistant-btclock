"""Switch entities: screen timer, DND, and Nostr/LED/focus setting toggles."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
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
    entities.extend(
        BtclockSettingsSwitch(coordinator, desc) for desc in SETTINGS_SWITCHES
    )
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
        self.coordinator.async_apply_optimistic({"timerRunning": True})

    async def async_turn_off(self, **_: Any) -> None:
        await self.coordinator.client.async_timer_stop()
        self.coordinator.async_apply_optimistic({"timerRunning": False})


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
        dnd = dict(self.coordinator.data.get("dnd") or {})
        dnd["enabled"] = True
        self.coordinator.async_apply_optimistic({"dnd": dnd})

    async def async_turn_off(self, **_: Any) -> None:
        await self.coordinator.client.async_dnd_disable()
        dnd = dict(self.coordinator.data.get("dnd") or {})
        dnd["enabled"] = False
        self.coordinator.async_apply_optimistic({"dnd": dnd})


@dataclass(frozen=True, kw_only=True)
class BtclockSettingsSwitchDescription(SwitchEntityDescription):
    """A boolean settings field that toggles via PATCH /api/settings."""

    setting_key: str
    available_fn: Callable[[BtclockCoordinator], bool] | None = None


SETTINGS_SWITCHES: tuple[BtclockSettingsSwitchDescription, ...] = (
    BtclockSettingsSwitchDescription(
        key="nostr_zap_notify",
        translation_key="nostr_zap_notify",
        icon="mdi:lightning-bolt",
        setting_key="nostrZapNotify",
    ),
    BtclockSettingsSwitchDescription(
        key="led_flash_on_zap",
        translation_key="led_flash_on_zap",
        icon="mdi:led-on",
        setting_key="ledFlashOnZap",
    ),
    BtclockSettingsSwitchDescription(
        key="led_flash_on_update",
        translation_key="led_flash_on_update",
        icon="mdi:led-on",
        setting_key="ledFlashOnUpd",
    ),
    BtclockSettingsSwitchDescription(
        key="steal_focus",
        translation_key="steal_focus",
        icon="mdi:target",
        setting_key="stealFocus",
    ),
)


class BtclockSettingsSwitch(BtclockEntity, SwitchEntity):
    """Writes a single boolean field via PATCH /api/settings."""

    entity_description: BtclockSettingsSwitchDescription

    def __init__(
        self,
        coordinator: BtclockCoordinator,
        description: BtclockSettingsSwitchDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return bool(
            self.coordinator.client.settings.get(self.entity_description.setting_key)
        )

    async def async_turn_on(self, **_: Any) -> None:
        await self.coordinator.async_patch_settings(
            {self.entity_description.setting_key: True}
        )

    async def async_turn_off(self, **_: Any) -> None:
        await self.coordinator.async_patch_settings(
            {self.entity_description.setting_key: False}
        )
