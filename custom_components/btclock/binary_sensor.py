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
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BtclockConfigEntry
from .coordinator import BtclockCoordinator
from .entity import BtclockEntity
from .models import DataSource


@dataclass(frozen=True, kw_only=True)
class BtclockBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[BtclockCoordinator], bool | None]
    available_fn: Callable[[BtclockCoordinator], bool] | None = None


def _data_source(c: BtclockCoordinator) -> int:
    return int(c.client.settings.get("dataSource") or 0)


def _price_feed_connected(c: BtclockCoordinator) -> bool | None:
    """Is the upstream providing price data connected? Logic per firmware.

    src/lib/system/config.cpp:388-407 — dataSource routes decide which
    connectionStatus flag is actually meaningful for price data:

      0 BTCLOCK / 3 CUSTOM → V2 relay
      1 THIRD_PARTY        → Kraken (connectionStatus.price)
      2 NOSTR              → Nostr pool
    """
    cs = c.data.get("connectionStatus") or {}
    match _data_source(c):
        case DataSource.THIRD_PARTY:
            return cs.get("price")
        case DataSource.NOSTR:
            return cs.get("nostr")
        case _:
            return cs.get("V2")


def _blocks_feed_connected(c: BtclockCoordinator) -> bool | None:
    cs = c.data.get("connectionStatus") or {}
    match _data_source(c):
        case DataSource.THIRD_PARTY:
            return cs.get("blocks")
        case DataSource.NOSTR:
            return cs.get("nostr")
        case _:
            return cs.get("V2")


BINARY_SENSORS: tuple[BtclockBinarySensorDescription, ...] = (
    BtclockBinarySensorDescription(
        key="price_connected",
        translation_key="price_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=_price_feed_connected,
    ),
    BtclockBinarySensorDescription(
        key="blocks_connected",
        translation_key="blocks_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=_blocks_feed_connected,
    ),
    BtclockBinarySensorDescription(
        key="v2_connected",
        translation_key="v2_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda c: (c.data.get("connectionStatus") or {}).get("V2"),
    ),
    BtclockBinarySensorDescription(
        key="timer_running",
        translation_key="timer_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda c: c.data.get("timerRunning"),
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

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator)
