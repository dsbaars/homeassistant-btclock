"""BlueprintEntity class."""
from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.core import callback

from .const import ATTRIBUTION, DOMAIN
from .coordinator import BtclockDataUpdateCoordinator


class BtclockEntity(CoordinatorEntity):
    """BtclockEntity class."""

    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: BtclockDataUpdateCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            name=coordinator.client._settings_data.get('hostname'),
            sw_version=coordinator.client._settings_data.get('gitRev'),
            model="V3"
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._ws_price_connected = self.coordinator.data["connectionStatus"]["price"]
        self._ws_block_connected = self.coordinator.data["connectionStatus"]["blocks"]
        self._current_screen = self.coordinator.data["currentScreen"]

        self.async_write_ha_state()
