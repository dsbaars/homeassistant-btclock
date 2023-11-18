"""Sensor platform for btclock."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .coordinator import BtclockDataUpdateCoordinator
from .entity import BtclockEntity

ENTITY_DESCRIPTIONS = (
    SelectEntityDescription(
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


class BtclockSensor(BtclockEntity, SelectEntity):
    """btclock Sensor class."""

    def __init__(
        self,
        coordinator: BtclockDataUpdateCoordinator,
        entity_description: SelectEntityDescription,
    ) -> None:
        """Initialize the sensor class."""
        self._attr_options = coordinator.client.get_screens()
        self.screenMap = coordinator.client.get_screens()
        super().__init__(coordinator)
        self.entity_description = entity_description

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
    def options(self) -> list[str]:
        """Return a set of selectable options."""
        return list(self.screenMap.values())

    @property
    def current_option(self) -> str:
        """Return the native value of the sensor."""
        return self.screenMap.get(self.coordinator.data.get("currentScreen"))

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        reverse_lookup = {value: key for key, value in self.screenMap.items()}

        await self.coordinator.client.async_set_screen(reverse_lookup.get(option))
        await self.coordinator.async_request_refresh()
