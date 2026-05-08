"""Integration-level services for BTClock.

These let a user drive focused device actions without touching the HTTP API
directly. Each service targets a specific device via its Home Assistant
device_id, looks up the loaded config entry, and routes the call through that
device's client.
"""

from __future__ import annotations

from typing import cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import DOMAIN
from .coordinator import BtclockCoordinator
from .models import ApiVariant, MODERN_VARIANTS

SERVICE_SHOW_TEXT = "show_text"
SERVICE_SHOW_CUSTOM = "show_custom"
SERVICE_TRIGGER_LED_EFFECT = "trigger_led_effect"
SERVICE_SET_FRONTLIGHT_CHANNELS = "set_frontlight_channels"

ATTR_DEVICE_ID = "device_id"
ATTR_TEXT = "text"
ATTR_SCREENS = "screens"
ATTR_EFFECT = "effect"
ATTR_DUTIES = "duties"

# Static upper bound used only as a guardrail for the YAML widget. All
# shipping firmware builds today have 7 screens, but some planned variants
# have 8 — hence 16 as the widget cap. The *actual* per-device limit is
# `numScreens` from /api/settings and is enforced at call time by the
# service handler below, so boards that grow a larger screen count never
# need an integration update.
_WIDGET_MAX_LEN: int = 16

LED_EFFECT_NAMES: tuple[str, ...] = (
    "blink",
    "blink_success",
    "blink_error",
    "rainbow",
    "breathe",
    "breathe_error",
    "zap",
    "identify",
    "heartbeat",
    "off",
    "idle",
)


def _uppercase_text(value: str) -> str:
    return value.upper() if isinstance(value, str) else value


_SHOW_TEXT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_TEXT): vol.All(
            cv.string,
            _uppercase_text,
            vol.Length(min=1, max=_WIDGET_MAX_LEN),
        ),
    }
)

_SHOW_CUSTOM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_SCREENS): vol.All(
            cv.ensure_list,
            [cv.string],
            vol.Length(min=1, max=_WIDGET_MAX_LEN),
        ),
    }
)

_TRIGGER_LED_EFFECT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_EFFECT): vol.In(LED_EFFECT_NAMES),
    }
)

_SET_FRONTLIGHT_CHANNELS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_DUTIES): vol.All(
            cv.ensure_list,
            [vol.All(vol.Coerce(int), vol.Range(min=0, max=4095))],
            vol.Length(max=_WIDGET_MAX_LEN),
        ),
    }
)


def _device_num_screens(coord: BtclockCoordinator) -> int:
    """Screens available on *this* device.

    Falls back to 7 (the ubiquitous value) if the setting is unexpectedly
    absent; the firmware clamps internally too.
    """
    value = coord.client.settings.get("numScreens")
    try:
        return int(value) if value is not None else 7
    except (TypeError, ValueError):
        return 7


def _coordinator_for_device(hass: HomeAssistant, device_id: str) -> BtclockCoordinator:
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise HomeAssistantError(f"Unknown device {device_id}")
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            continue
        if entry.state is not ConfigEntryState.LOADED:
            raise HomeAssistantError(
                f"BTClock {device.name or device_id} is not loaded"
            )
        return cast(BtclockCoordinator, entry.runtime_data)
    raise HomeAssistantError(f"Device {device_id} is not a BTClock")


async def async_register_services(hass: HomeAssistant) -> None:
    """Register the domain-level services exactly once per HA lifetime."""
    if hass.services.has_service(DOMAIN, SERVICE_SHOW_TEXT):
        return

    def _require_v4(coord: BtclockCoordinator, service_name: str) -> None:
        if coord.client.variant is not ApiVariant.V4:
            raise HomeAssistantError(f"btclock.{service_name} requires v4 firmware")

    async def _handle_show_text(call: ServiceCall) -> None:
        coord = _coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
        if coord.client.variant not in MODERN_VARIANTS:
            raise HomeAssistantError(
                "btclock.show_text requires firmware 3.4.0 or newer"
            )
        num_screens = _device_num_screens(coord)
        text: str = call.data[ATTR_TEXT]
        if len(text) > num_screens:
            raise HomeAssistantError(
                f"Text is {len(text)} characters long, but this BTClock has "
                f"only {num_screens} screens"
            )
        await coord.client.async_show_text(text)

    async def _handle_show_custom(call: ServiceCall) -> None:
        coord = _coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
        if coord.client.variant not in MODERN_VARIANTS:
            raise HomeAssistantError(
                "btclock.show_custom requires firmware 3.4.0 or newer"
            )
        num_screens = _device_num_screens(coord)
        screens: list[str] = call.data[ATTR_SCREENS]
        if len(screens) > num_screens:
            raise HomeAssistantError(
                f"{len(screens)} screen strings provided, but this BTClock "
                f"has only {num_screens} screens"
            )
        await coord.client.async_show_custom(screens)

    async def _handle_trigger_led_effect(call: ServiceCall) -> None:
        coord = _coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
        _require_v4(coord, SERVICE_TRIGGER_LED_EFFECT)
        await coord.client.async_trigger_light_effect(call.data[ATTR_EFFECT])

    async def _handle_set_frontlight_channels(call: ServiceCall) -> None:
        coord = _coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
        _require_v4(coord, SERVICE_SET_FRONTLIGHT_CHANNELS)
        if not coord.client.settings.get("hasFrontlight"):
            raise HomeAssistantError("This BTClock does not have a frontlight")
        num_screens = _device_num_screens(coord)
        duties: list[int] = call.data[ATTR_DUTIES]
        if duties and len(duties) != num_screens:
            raise HomeAssistantError(
                f"{len(duties)} frontlight values provided, but this BTClock "
                f"has {num_screens} screens"
            )
        await coord.client.async_set_frontlight_channels(duties)
        coord.async_apply_optimistic(
            {"flStatus": duties if duties else [0] * num_screens}
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SHOW_TEXT, _handle_show_text, schema=_SHOW_TEXT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SHOW_CUSTOM, _handle_show_custom, schema=_SHOW_CUSTOM_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TRIGGER_LED_EFFECT,
        _handle_trigger_led_effect,
        schema=_TRIGGER_LED_EFFECT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FRONTLIGHT_CHANNELS,
        _handle_set_frontlight_channels,
        schema=_SET_FRONTLIGHT_CHANNELS_SCHEMA,
    )
