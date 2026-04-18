"""Coordinator behaviour — SSE push forwards to entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.btclock.const import DOMAIN
from custom_components.btclock.coordinator import BtclockCoordinator
from custom_components.btclock.models import ApiVariant


def _make_mock_client(settings: dict) -> MagicMock:
    client = MagicMock()
    client.host = "btclock-test.local"
    client.variant = ApiVariant.V3_4
    client.settings = settings
    client.async_update_status = AsyncMock(return_value={"currentScreen": 0})
    return client


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="btclock-test",
        data={CONF_HOST: "btclock-test.local"},
    )
    entry.add_to_hass(hass)
    return entry


async def test_sse_status_frame_updates_coordinator_data(
    hass: HomeAssistant, config_entry: MockConfigEntry, load_fixture
) -> None:
    client = _make_mock_client(load_fixture("settings_v3_4_revb"))
    coord = BtclockCoordinator(hass, config_entry, client)

    status_frame = load_fixture("status_v3_4_revb")
    await coord._on_status_frame(status_frame)  # noqa: SLF001

    assert coord.data == status_frame
    assert coord.data["currentScreen"] == status_frame["currentScreen"]


async def test_poll_heartbeat_calls_update_status(
    hass: HomeAssistant, config_entry: MockConfigEntry, load_fixture
) -> None:
    client = _make_mock_client(load_fixture("settings_v3_4_revb"))
    expected = {"currentScreen": 5, "timerRunning": True, "leds": []}
    client.async_update_status.return_value = expected

    coord = BtclockCoordinator(hass, config_entry, client)
    data = await coord._async_update_data()  # noqa: SLF001

    assert data == expected
    client.async_update_status.assert_awaited_once()
