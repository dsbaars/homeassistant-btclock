"""Switch entities: screen timer, DND, and Nostr/LED/focus setting toggles."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
        entities.append(BtclockDndTimeEnabledSwitch(coordinator))
    entities.extend(
        BtclockSettingsSwitch(coordinator, desc) for desc in SETTINGS_SWITCHES
    )
    async_add_entities(entities)


def merged_dnd_patch(coordinator: BtclockCoordinator, **changes: Any) -> dict:
    """Build a {"dnd": {...}} PATCH body carrying every existing dnd field
    plus the supplied changes. The coordinator's top-level settings merge
    would otherwise clobber unspecified dnd keys in the optimistic cache."""
    current = dict(coordinator.client.settings.get("dnd") or {})
    current.update(changes)
    return {"dnd": current}


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
        # Reflect the effective DND state: true when either the manual flag or
        # the scheduled quiet-hours window is active on the device.
        dnd = self.coordinator.data.get("dnd") or {}
        if "active" in dnd:
            return dnd.get("active")
        return dnd.get("enabled")

    async def async_turn_on(self, **_: Any) -> None:
        await self.coordinator.client.async_dnd_enable()
        dnd = dict(self.coordinator.data.get("dnd") or {})
        dnd["enabled"] = True
        dnd["active"] = True
        self.coordinator.async_apply_optimistic({"dnd": dnd})

    async def async_turn_off(self, **_: Any) -> None:
        if _schedule_covers_now(self.coordinator):
            raise HomeAssistantError(
                "Do Not Disturb is held on by the scheduled quiet hours; "
                "disable the DND schedule in the device settings to turn it off."
            )
        await self.coordinator.client.async_dnd_disable()
        dnd = dict(self.coordinator.data.get("dnd") or {})
        dnd["enabled"] = False
        dnd["active"] = False
        self.coordinator.async_apply_optimistic({"dnd": dnd})


class BtclockDndTimeEnabledSwitch(BtclockEntity, SwitchEntity):
    """Toggles the scheduled quiet-hours feature (settings.dnd.dndTimeEnabled)."""

    _attr_translation_key = "dnd_time_enabled"
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: BtclockCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_dnd_time_enabled"

    @property
    def is_on(self) -> bool | None:
        cfg = self.coordinator.client.settings.get("dnd") or {}
        return cfg.get("dndTimeEnabled")

    async def async_turn_on(self, **_: Any) -> None:
        await self.coordinator.async_patch_settings(
            merged_dnd_patch(self.coordinator, dndTimeEnabled=True)
        )

    async def async_turn_off(self, **_: Any) -> None:
        await self.coordinator.async_patch_settings(
            merged_dnd_patch(self.coordinator, dndTimeEnabled=False)
        )


def _schedule_covers_now(coordinator: BtclockCoordinator) -> bool:
    """Is the device's DND quiet-hours window currently covering 'now'?

    Uses the schedule fields from /api/settings (startHour/Minute,
    endHour/Minute) and the device's tzString. Handles overnight windows
    where start > end (e.g. 23:00 → 07:00).
    """
    settings = coordinator.client.settings
    cfg = settings.get("dnd") or {}
    if not cfg.get("dndTimeEnabled"):
        return False
    try:
        tz = ZoneInfo(settings.get("tzString") or "UTC")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    now = datetime.now(tz).time()
    start = time(int(cfg.get("startHour", 0)), int(cfg.get("startMinute", 0)))
    end = time(int(cfg.get("endHour", 0)), int(cfg.get("endMinute", 0)))
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


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
    BtclockSettingsSwitchDescription(
        key="disable_leds",
        translation_key="disable_leds",
        icon="mdi:led-off",
        setting_key="disableLeds",
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
