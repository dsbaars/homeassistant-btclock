"""Diagnostics download for a BTClock config entry."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import BtclockConfigEntry

_REDACT_ENTRY = {CONF_HOST, CONF_USERNAME, CONF_PASSWORD}
_REDACT_SETTINGS = {
    "hostname",
    "hostnamePrefix",
    "ip",
    "httpAuthUser",
    "httpAuthPass",
    "nostrPubKey",
    "nostrZapPubkey",
    "bitaxeHostname",
    "miningPoolUser",
    "ceEndpoint",
    "customEndpoint",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BtclockConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), _REDACT_ENTRY),
        "variant": coordinator.client.variant.value,
        "settings": async_redact_data(coordinator.client.settings, _REDACT_SETTINGS),
        "status": coordinator.data,
    }
