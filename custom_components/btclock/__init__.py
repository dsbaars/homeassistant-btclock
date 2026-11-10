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
from .const import LOGGER
from .coordinator import BtclockCoordinator
from .host_utils import is_mdns_host, usable_ipv4
from .services import async_register_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
    Platform.UPDATE,
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
        settings = await client.async_load_settings()
    except BtclockAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except BtclockCommunicationError as err:
        raise ConfigEntryNotReady(str(err)) from err

    # Entries created before the integration stored IPs hold the device's
    # .local name. Now that it answered, switch to the IP it reports so
    # later connects no longer depend on an mDNS lookup. Runs before the
    # update listener is attached, so this does not trigger a reload.
    if is_mdns_host(entry.data[CONF_HOST]) and (ip := usable_ipv4(settings.get("ip"))):
        LOGGER.info(
            "Storing IP %s for %s instead of its .local name",
            ip,
            entry.data[CONF_HOST],
        )
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_HOST: ip}
        )
        client.set_host(ip)

    coordinator = BtclockCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await coordinator.async_start()
    await async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BtclockConfigEntry) -> bool:
    """Unload a config entry — stop the update machinery and tear down platforms."""
    coordinator = entry.runtime_data
    await coordinator.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: BtclockConfigEntry
) -> None:
    """Reload when options or data change."""
    await hass.config_entries.async_reload(entry.entry_id)
