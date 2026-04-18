"""BTClock integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    BtclockAuthError,
    BtclockClient,
    BtclockCommunicationError,
)
from .coordinator import BtclockCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

type BtclockConfigEntry = ConfigEntry[BtclockCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: BtclockConfigEntry) -> bool:
    """Set up a BTClock device from a config entry."""
    client = BtclockClient(
        host=entry.data[CONF_HOST],
        session=async_get_clientsession(hass),
        username=entry.data.get(CONF_USERNAME),
        password=entry.data.get(CONF_PASSWORD),
    )

    try:
        await client.async_load_settings()
    except BtclockAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except BtclockCommunicationError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = BtclockCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await coordinator.async_start_push()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BtclockConfigEntry) -> bool:
    """Unload a config entry — stop the SSE task and tear down platforms."""
    coordinator = entry.runtime_data
    await coordinator.async_stop_push()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: BtclockConfigEntry
) -> None:
    """Reload when options or data change."""
    await hass.config_entries.async_reload(entry.entry_id)
