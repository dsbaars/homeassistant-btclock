"""Binary sensor platform for integration_blueprint."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .const import DOMAIN
from .coordinator import BtclockDataUpdateCoordinator
from .entity import BtclockEntity
from homeassistant.helpers.entity import DeviceInfo

conn_status_map = {'btclock_price': 'price', 'btclock_blocks': 'blocks'}


ENTITY_DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="btclock_price",
        name="Price data source",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    BinarySensorEntityDescription(
        key="btclock_blocks",
        name="Blocks data source",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    BinarySensorEntityDescription(
        key="btclock_timer_active",
        name="Timer active",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
)


async def async_setup_entry(hass, entry, async_add_devices):
    """Set up the binary_sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_devices(
        BtclockBinarySensor(
            coordinator=coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
    )


class BtclockBinarySensor(BtclockEntity, BinarySensorEntity):
    """btclcok_integration binary_sensor class."""

    def __init__(
        self,
        coordinator: BtclockDataUpdateCoordinator,
        entity_description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary_sensor class."""
        self.key = entity_description.key
        self.entity_description = entity_description
       #self.name = entity_description.key
        super().__init__(coordinator)

    @property
    def device_info(self):
        """Return the Device info for this sensor."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name=self.coordinator.client._settings_data.get('hostname'),
            sw_version=self.coordinator.client._settings_data.get('gitRev'),
            model="V3"
        )

    @property
    def unique_id(self):
        """Return the unique ID for this sensor."""
        return self.coordinator.config_entry.entry_id + "_" + self.key


    @property
    def is_on(self) -> bool:
        """Return true if the binary_sensor is on."""
        if (self.key == "btclock_timer_active"):
            return self.coordinator.data.get("timerRunning")
        else:
            return self.coordinator.data.get("connectionStatus").get(conn_status_map.get(self.entity_description.key))
