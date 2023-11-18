"""Sensor platform for integration_blueprint."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription

from .const import DOMAIN
from .coordinator import BtclockDataUpdateCoordinator
from .entity import BtclockEntity

ENTITY_DESCRIPTIONS = (
    SensorEntityDescription(
        key="btclock_screen",
        name="Current screen",
        icon="mdi:monitor",
    ),
)


async def async_setup_entry(hass, entry, async_add_devices):
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_devices(
        BtclockSensor(
            coordinator=coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
    )


class BtclockSensor(BtclockEntity, SensorEntity):
    """integration_blueprint Sensor class."""

    def __init__(
        self,
        coordinator: BtclockDataUpdateCoordinator,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor class."""
        self.screenMap = coordinator.client.get_screens()
        super().__init__(coordinator)
        self.entity_description = entity_description

    @property
    def device_info(self):
        """Return the Device info for this sensor."""
        return self._attr_device_info

    @property
    def native_value(self) -> str:
        """Return the native value of the sensor."""
        return self.screenMap.get(self.coordinator.data.get("currentScreen"))
