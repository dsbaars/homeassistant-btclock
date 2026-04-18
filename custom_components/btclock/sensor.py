"""Sensor entities."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    LIGHT_LUX,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BtclockConfigEntry
from .coordinator import BtclockCoordinator
from .entity import BtclockEntity


@dataclass(frozen=True, kw_only=True)
class BtclockSensorDescription(SensorEntityDescription):
    value_fn: Callable[[BtclockCoordinator], Any]
    attrs_fn: Callable[[BtclockCoordinator], Mapping[str, Any]] | None = None
    available_fn: Callable[[BtclockCoordinator], bool] | None = None


def _screen_name(coordinator: BtclockCoordinator) -> str | None:
    screens = coordinator.client.settings.get("screens") or []
    current = coordinator.data.get("currentScreen")
    if current is None:
        return None
    for s in screens:
        if s.get("id") == current:
            return s.get("name")
    return None


def _ota_state(c: BtclockCoordinator) -> str:
    return "updating" if c.data.get("isOTAUpdating") else "idle"


def _nostr_relay(c: BtclockCoordinator) -> str | None:
    return c.client.settings.get("nostrRelay") or None


def _nostr_relay_attrs(c: BtclockCoordinator) -> Mapping[str, Any]:
    cs = c.data.get("connectionStatus") or {}
    return {"connected": bool(cs.get("nostr"))}


SENSORS: tuple[BtclockSensorDescription, ...] = (
    BtclockSensorDescription(
        key="current_screen",
        translation_key="current_screen",
        icon="mdi:monitor",
        value_fn=_screen_name,
    ),
    BtclockSensorDescription(
        key="currency",
        translation_key="currency",
        icon="mdi:currency-usd",
        value_fn=lambda c: c.data.get("currency"),
    ),
    BtclockSensorDescription(
        key="nostr_relay",
        translation_key="nostr_relay",
        icon="mdi:satellite-variant",
        value_fn=_nostr_relay,
        attrs_fn=_nostr_relay_attrs,
        available_fn=lambda c: bool(c.client.settings.get("nostrRelay")),
    ),
    BtclockSensorDescription(
        key="light_level",
        translation_key="light_level",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement=LIGHT_LUX,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.data.get("lightLevel"),
        available_fn=lambda c: bool(c.client.settings.get("hasLightLevel")),
    ),
    BtclockSensorDescription(
        key="ota_state",
        translation_key="ota_state",
        device_class=SensorDeviceClass.ENUM,
        options=["idle", "updating"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_ota_state,
    ),
    BtclockSensorDescription(
        key="rssi",
        translation_key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.get("rssi"),
    ),
    BtclockSensorDescription(
        key="uptime",
        translation_key="uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.get("espUptime"),
    ),
    BtclockSensorDescription(
        key="free_heap",
        translation_key="free_heap",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.get("espFreeHeap"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BtclockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        BtclockSensor(coordinator, desc)
        for desc in SENSORS
        if desc.available_fn is None or desc.available_fn(coordinator)
    )


class BtclockSensor(BtclockEntity, SensorEntity):
    entity_description: BtclockSensorDescription

    def __init__(
        self,
        coordinator: BtclockCoordinator,
        description: BtclockSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator)
