"""Integration-level services: btclock.show_text and btclock.show_custom."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.btclock.api import BtclockClient
from custom_components.btclock.const import DOMAIN
from custom_components.btclock.models import ApiVariant
from custom_components.btclock.services import SERVICE_SHOW_CUSTOM, SERVICE_SHOW_TEXT


async def _setup(
    hass: HomeAssistant,
    settings: dict,
    status: dict,
    *,
    variant: ApiVariant,
    mock_aioresponse=None,
) -> str:
    """Set up a config entry with the given settings and return its device_id."""
    if mock_aioresponse is not None:
        mock_aioresponse.get(
            "https://git.btclock.dev/api/v1/repos/btclock/btclock_v3/releases/latest",
            status=404,
            repeat=True,
        )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=settings["hostname"],
        data={CONF_HOST: settings["hostname"] + ".local"},
    )
    entry.add_to_hass(hass)

    async def _fake_load(self: BtclockClient) -> dict:
        self._settings = settings  # noqa: SLF001
        self._variant = variant  # noqa: SLF001
        return settings

    with (
        patch.object(BtclockClient, "async_load_settings", _fake_load),
        patch.object(
            BtclockClient, "async_update_status", new=AsyncMock(return_value=status)
        ),
        patch(
            "custom_components.btclock.coordinator.BtclockCoordinator.async_start",
            new=AsyncMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    return device.id


async def test_show_text_calls_api(
    hass: HomeAssistant, load_fixture, mock_aioresponse
) -> None:
    device_id = await _setup(
        hass,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        variant=ApiVariant.V3_4,
        mock_aioresponse=mock_aioresponse,
    )
    with patch.object(BtclockClient, "async_show_text", new=AsyncMock()) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SHOW_TEXT,
            {"device_id": device_id, "text": "HODL"},
            blocking=True,
        )
    mock_call.assert_awaited_once_with("HODL")


async def test_show_text_uppercases_input(
    hass: HomeAssistant, load_fixture, mock_aioresponse
) -> None:
    device_id = await _setup(
        hass,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        variant=ApiVariant.V3_4,
        mock_aioresponse=mock_aioresponse,
    )
    with patch.object(BtclockClient, "async_show_text", new=AsyncMock()) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SHOW_TEXT,
            {"device_id": device_id, "text": "hodl"},
            blocking=True,
        )
    mock_call.assert_awaited_once_with("HODL")


async def test_show_text_rejects_over_device_num_screens(
    hass: HomeAssistant, load_fixture, mock_aioresponse
) -> None:
    """Rev B fixture reports numScreens=7 → 8-char input is rejected per device."""
    device_id = await _setup(
        hass,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        variant=ApiVariant.V3_4,
        mock_aioresponse=mock_aioresponse,
    )
    with pytest.raises(HomeAssistantError, match="only 7 screens"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SHOW_TEXT,
            {"device_id": device_id, "text": "TOOLONG8"},
            blocking=True,
        )


async def test_show_text_accepts_device_specific_max(
    hass: HomeAssistant, load_fixture, mock_aioresponse
) -> None:
    """An 8-screen device accepts 8 characters; a 7-screen device rejects the 8th."""
    settings = load_fixture("settings_v3_4_revb").copy()
    settings["numScreens"] = 8
    device_id = await _setup(
        hass,
        settings,
        load_fixture("status_v3_4_revb"),
        variant=ApiVariant.V3_4,
        mock_aioresponse=mock_aioresponse,
    )
    with patch.object(BtclockClient, "async_show_text", new=AsyncMock()) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SHOW_TEXT,
            {"device_id": device_id, "text": "HODLOIAG"},
            blocking=True,
        )
    mock_call.assert_awaited_once_with("HODLOIAG")


async def test_show_text_rejects_above_widget_cap(
    hass: HomeAssistant, load_fixture, mock_aioresponse
) -> None:
    """Schema-level guardrail: > 16 chars never reach the handler."""
    device_id = await _setup(
        hass,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        variant=ApiVariant.V3_4,
        mock_aioresponse=mock_aioresponse,
    )
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SHOW_TEXT,
            {"device_id": device_id, "text": "A" * 17},
            blocking=True,
        )


async def test_show_custom_rejects_too_many_entries(
    hass: HomeAssistant, load_fixture, mock_aioresponse
) -> None:
    device_id = await _setup(
        hass,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        variant=ApiVariant.V3_4,
        mock_aioresponse=mock_aioresponse,
    )
    with pytest.raises(HomeAssistantError, match="only 7 screens"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SHOW_CUSTOM,
            {"device_id": device_id, "screens": list("ABCDEFGH")},
            blocking=True,
        )


async def test_show_custom_calls_api(
    hass: HomeAssistant, load_fixture, mock_aioresponse
) -> None:
    device_id = await _setup(
        hass,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        variant=ApiVariant.V3_4,
        mock_aioresponse=mock_aioresponse,
    )
    screens = ["B", "T", "C", "L", "O", "C", "K"]
    with patch.object(BtclockClient, "async_show_custom", new=AsyncMock()) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SHOW_CUSTOM,
            {"device_id": device_id, "screens": screens},
            blocking=True,
        )
    mock_call.assert_awaited_once_with(screens)


async def test_show_text_refused_on_legacy(hass: HomeAssistant, load_fixture) -> None:
    # Legacy firmware has no update entity, so no outbound URL to mock.
    device_id = await _setup(
        hass,
        load_fixture("settings_legacy"),
        load_fixture("status_legacy"),
        variant=ApiVariant.LEGACY,
    )
    with pytest.raises(HomeAssistantError, match="3.4.0"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SHOW_TEXT,
            {"device_id": device_id, "text": "HODL"},
            blocking=True,
        )


async def test_show_text_unknown_device_raises(
    hass: HomeAssistant, load_fixture, mock_aioresponse
) -> None:
    await _setup(
        hass,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        variant=ApiVariant.V3_4,
        mock_aioresponse=mock_aioresponse,
    )
    with pytest.raises(HomeAssistantError, match="Unknown device"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SHOW_TEXT,
            {"device_id": "does-not-exist", "text": "HODL"},
            blocking=True,
        )
