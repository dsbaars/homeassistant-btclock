"""DataUpdateCoordinator for btclock."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .btclock import Btclock, BtclockClientError
from .const import DOMAIN, LOGGER, DEFAULT_SCAN_INTERVAL


# https://developers.home-assistant.io/docs/integration_fetching_data#coordinated-single-api-poll-for-data-for-all-entities
class BtclockDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: Btclock,
    ) -> None:
        """Initialize."""
        self.client = client
        self.config_entry = config_entry

        super().__init__(
            hass=hass,
            logger=LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )

    async def _async_update_data(self):
        """Update data via library."""
        try:
            await self.client.update_status()
            return self.client._status_data
        except BtclockClientError as exception:
            raise UpdateFailed(exception) from exception
