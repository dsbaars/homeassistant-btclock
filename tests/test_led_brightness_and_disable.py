"""Settings-backed LED brightness slider + disable LEDs switch."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.btclock.api import BtclockClient
from custom_components.btclock.const import DOMAIN
from custom_components.btclock.models import ApiVariant


async def _setup(
    hass: HomeAssistant,
    settings: dict,
    status: dict,
    *,
    mock_aioresponse,
) -> MockConfigEntry:
    # Any HTTP call to the release URL is short-circuited — nothing here
    # cares about the update entity, but its release coordinator still runs.
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
        self._settings = dict(settings)  # noqa: SLF001
        self._variant = ApiVariant.V3_4  # noqa: SLF001
        return self._settings  # noqa: SLF001

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
    return entry


async def test_led_brightness_entity_reflects_setting(
    hass: HomeAssistant, load_fixture, mock_aioresponse
) -> None:
    await _setup(
        hass,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        mock_aioresponse=mock_aioresponse,
    )
    state = hass.states.get("number.btclock_9d5530_led_brightness")
    assert state is not None
    assert float(state.state) == 128.0
    assert state.attributes["min"] == 0
    assert state.attributes["max"] == 255


async def test_led_brightness_set_value_patches_settings(
    hass: HomeAssistant, load_fixture, mock_aioresponse
) -> None:
    await _setup(
        hass,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        mock_aioresponse=mock_aioresponse,
    )
    with patch.object(
        BtclockClient, "async_patch_settings", new=AsyncMock()
    ) as mock_patch:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.btclock_9d5530_led_brightness", "value": 200},
            blocking=True,
        )
    mock_patch.assert_awaited_once_with({"ledBrightness": 200})


async def test_disable_leds_switch_off_initially(
    hass: HomeAssistant, load_fixture, mock_aioresponse
) -> None:
    await _setup(
        hass,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        mock_aioresponse=mock_aioresponse,
    )
    state = hass.states.get("switch.btclock_9d5530_disable_leds")
    assert state is not None
    assert state.state == "off"


async def test_disable_leds_switch_turn_on_patches_settings(
    hass: HomeAssistant, load_fixture, mock_aioresponse
) -> None:
    await _setup(
        hass,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        mock_aioresponse=mock_aioresponse,
    )
    with patch.object(
        BtclockClient, "async_patch_settings", new=AsyncMock()
    ) as mock_patch:
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.btclock_9d5530_disable_leds"},
            blocking=True,
        )
    mock_patch.assert_awaited_once_with({"disableLeds": True})
