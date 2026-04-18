"""Binary sensor entities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BtclockConfigEntry
from .coordinator import BtclockCoordinator
from .entity import BtclockEntity


@dataclass(frozen=True, kw_only=True)
class BtclockBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[BtclockCoordinator], bool | None]
    available_fn: Callable[[BtclockCoordinator], bool] | None = None
    # When set, overrides entity_registry_enabled_default at setup time based
    # on live device state. Used to auto-enable the V2/nostr sensors on
    # devices whose dataSource actually uses those feeds.
    enabled_default_fn: Callable[[BtclockCoordinator], bool] | None = None


def _conn(key: str) -> Callable[[BtclockCoordinator], bool | None]:
    def _fn(c: BtclockCoordinator) -> bool | None:
        cs = c.data.get("connectionStatus") or {}
        return cs.get(key)

    return _fn


def _conn_active_at_setup(key: str) -> Callable[[BtclockCoordinator], bool]:
    """Enable-by-default if this feed is currently reporting connected."""

    def _fn(c: BtclockCoordinator) -> bool:
        cs = c.data.get("connectionStatus") or {}
        return bool(cs.get(key))

    return _fn


BINARY_SENSORS: tuple[BtclockBinarySensorDescription, ...] = (
    BtclockBinarySensorDescription(
        key="price_connected",
        translation_key="price_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=_conn("price"),
        enabled_default_fn=_conn_active_at_setup("price"),
    ),
    BtclockBinarySensorDescription(
        key="blocks_connected",
        translation_key="blocks_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=_conn("blocks"),
        enabled_default_fn=_conn_active_at_setup("blocks"),
    ),
    BtclockBinarySensorDescription(
        key="v2_connected",
        translation_key="v2_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_conn("V2"),
        enabled_default_fn=_conn_active_at_setup("V2"),
    ),
    BtclockBinarySensorDescription(
        key="nostr_connected",
        translation_key="nostr_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_conn("nostr"),
        enabled_default_fn=_conn_active_at_setup("nostr"),
    ),
    BtclockBinarySensorDescription(
        key="timer_running",
        translation_key="timer_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda c: c.data.get("timerRunning"),
    ),
    BtclockBinarySensorDescription(
        key="ota_updating",
        translation_key="ota_updating",
        device_class=BinarySensorDeviceClass.UPDATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.get("isOTAUpdating"),
    ),
    BtclockBinarySensorDescription(
        key="dnd_active",
        translation_key="dnd_active",
        value_fn=lambda c: (c.data.get("dnd") or {}).get("active"),
        available_fn=lambda c: "dnd" in (c.data or {}),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BtclockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        BtclockBinarySensor(coordinator, desc)
        for desc in BINARY_SENSORS
        if desc.available_fn is None or desc.available_fn(coordinator)
    )


class BtclockBinarySensor(BtclockEntity, BinarySensorEntity):
    entity_description: BtclockBinarySensorDescription

    def __init__(
        self,
        coordinator: BtclockCoordinator,
        description: BtclockBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        if description.enabled_default_fn is not None:
            # Override the description's static default with the live-state check.
            # Any-key=True wins; we don't *disable* a sensor that the description
            # defaulted to enabled.
            if description.enabled_default_fn(coordinator):
                self._attr_entity_registry_enabled_default = True
            elif description.entity_registry_enabled_default is False:
                self._attr_entity_registry_enabled_default = False

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator)
