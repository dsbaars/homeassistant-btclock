"""Optimistic-update regression tests.

These lock in the behaviour from v0.4.1: any control (light, switch,
select) must apply its new state to `coordinator.data` immediately after
a successful write, so the UI doesn't hang on an SSE/poll round-trip.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.btclock.api import BtclockClient
from custom_components.btclock.const import DOMAIN
from custom_components.btclock.models import ApiVariant


async def _setup(hass: HomeAssistant, settings: dict, status: dict) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=settings["hostname"],
        data={CONF_HOST: settings["hostname"] + ".local"},
    )
    entry.add_to_hass(hass)

    async def _fake_load(self: BtclockClient) -> dict:
        self._settings = settings  # noqa: SLF001
        self._variant = ApiVariant.V3_4  # noqa: SLF001
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
    return entry


@pytest.fixture
def status_leds_off(load_fixture) -> dict:
    status = load_fixture("status_v3_4_revb").copy()
    status["leds"] = [
        {"hex": "#000000", "red": 0, "green": 0, "blue": 0},
        {"hex": "#000000", "red": 0, "green": 0, "blue": 0},
        {"hex": "#000000", "red": 0, "green": 0, "blue": 0},
        {"hex": "#000000", "red": 0, "green": 0, "blue": 0},
    ]
    return status


async def test_led_turn_on_updates_state_without_refresh(
    hass: HomeAssistant, load_fixture, status_leds_off
) -> None:
    """Flipping an LED on should mark it on in coordinator.data *before* any
    refresh happens — proves the optimistic path."""
    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status_leds_off)
    coord = entry.runtime_data

    refreshed = False

    async def _boom(*_a, **_kw):
        nonlocal refreshed
        refreshed = True

    with (
        patch.object(BtclockClient, "async_set_lights", new=AsyncMock()),
        patch.object(coord, "async_request_refresh", side_effect=_boom),
    ):
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": "light.btclock_9d5530_led_1", "rgb_color": [255, 204, 0]},
            blocking=True,
        )

    assert refreshed is False, "optimistic path must not request a refresh"
    state = hass.states.get("light.btclock_9d5530_led_1")
    assert state.state == "on"
    assert state.attributes.get("rgb_color") == (255, 204, 0)
    # coordinator.data's leds[0] should reflect the new value
    assert coord.data["leds"][0]["hex"] == "#FFCC00"
    assert coord.data["leds"][0]["red"] == 255


async def test_led_turn_off_updates_state_without_refresh(
    hass: HomeAssistant, load_fixture
) -> None:
    status = load_fixture("status_v3_4_revb")
    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status)
    coord = entry.runtime_data

    with (
        patch.object(BtclockClient, "async_set_lights", new=AsyncMock()),
        patch.object(coord, "async_request_refresh") as refresh_mock,
    ):
        await hass.services.async_call(
            "light",
            "turn_off",
            {"entity_id": "light.btclock_9d5530_led_1"},
            blocking=True,
        )

    refresh_mock.assert_not_called()
    assert coord.data["leds"][0]["hex"] == "#000000"


async def test_timer_switch_optimistic(hass: HomeAssistant, load_fixture) -> None:
    status = load_fixture("status_v3_4_revb").copy()
    status["timerRunning"] = False
    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status)
    coord = entry.runtime_data

    with (
        patch.object(BtclockClient, "async_timer_start", new=AsyncMock()),
        patch.object(coord, "async_request_refresh") as refresh_mock,
    ):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.btclock_9d5530_screen_timer"},
            blocking=True,
        )

    refresh_mock.assert_not_called()
    assert coord.data["timerRunning"] is True


async def test_screen_select_optimistic(hass: HomeAssistant, load_fixture) -> None:
    status = load_fixture("status_v3_4_revb").copy()
    status["currentScreen"] = 0
    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status)
    coord = entry.runtime_data

    with (
        patch.object(BtclockClient, "async_set_screen", new=AsyncMock()),
        patch.object(coord, "async_request_refresh") as refresh_mock,
    ):
        await hass.services.async_call(
            "select",
            "select_option",
            {
                "entity_id": "select.btclock_9d5530_screen",
                "option": "Market cap",
            },
            blocking=True,
        )

    refresh_mock.assert_not_called()
    assert coord.data["currentScreen"] == 1
