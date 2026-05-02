"""Coordinator behaviour — both update modes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.btclock.const import (
    CONF_UPDATE_MODE,
    DOMAIN,
    UPDATE_MODE_EVENTS,
    UPDATE_MODE_POLLING,
)
from custom_components.btclock.coordinator import BtclockCoordinator
from custom_components.btclock.models import ApiVariant


def _make_mock_client(settings: dict) -> MagicMock:
    client = MagicMock()
    client.host = "btclock-test.local"
    client.variant = ApiVariant.V3_4
    client.settings = settings
    client.async_update_status = AsyncMock(return_value={"currentScreen": 0})
    return client


def _entry(hass: HomeAssistant, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="btclock-test",
        data={CONF_HOST: "btclock-test.local"},
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    return _entry(hass)


async def test_sse_status_frame_updates_coordinator_data(
    hass: HomeAssistant, config_entry: MockConfigEntry, load_fixture
) -> None:
    client = _make_mock_client(load_fixture("settings_v3_4_revb"))
    coord = BtclockCoordinator(hass, config_entry, client)

    status_frame = load_fixture("status_v3_4_revb")
    await coord._on_status_frame(status_frame)  # noqa: SLF001

    assert coord.data == status_frame


async def test_events_mode_leaves_update_interval_none(
    hass: HomeAssistant, load_fixture
) -> None:
    entry = _entry(hass, {CONF_UPDATE_MODE: UPDATE_MODE_EVENTS, CONF_SCAN_INTERVAL: 30})
    client = _make_mock_client(load_fixture("settings_v3_4_revb"))

    coord = BtclockCoordinator(hass, entry, client)

    assert coord.update_mode == UPDATE_MODE_EVENTS
    assert coord.update_interval is None


async def test_polling_mode_sets_update_interval(
    hass: HomeAssistant, load_fixture
) -> None:
    entry = _entry(
        hass, {CONF_UPDATE_MODE: UPDATE_MODE_POLLING, CONF_SCAN_INTERVAL: 15}
    )
    client = _make_mock_client(load_fixture("settings_v3_4_revb"))

    coord = BtclockCoordinator(hass, entry, client)

    assert coord.update_mode == UPDATE_MODE_POLLING
    assert coord.update_interval is not None
    assert coord.update_interval.total_seconds() == 15


async def test_polling_mode_uses_status_endpoint(
    hass: HomeAssistant, config_entry: MockConfigEntry, load_fixture
) -> None:
    client = _make_mock_client(load_fixture("settings_v3_4_revb"))
    expected = {"currentScreen": 5, "timerRunning": True, "leds": []}
    client.async_update_status.return_value = expected

    coord = BtclockCoordinator(hass, config_entry, client)
    data = await coord._async_update_data()  # noqa: SLF001

    assert data == expected
    client.async_update_status.assert_awaited_once()


async def test_status_merge_preserves_flStatus_on_v4(
    hass: HomeAssistant, config_entry: MockConfigEntry, load_fixture
) -> None:
    """v4 firmware omits flStatus from /api/status; the previously cached
    value must survive subsequent updates so the frontlight light entity
    doesn't flicker back to "off" on every status frame."""
    client = _make_mock_client(load_fixture("settings_v4_revb"))
    coord = BtclockCoordinator(hass, config_entry, client)

    # Bootstrap-equivalent: seed flStatus (as light.async_setup_entry would).
    coord.async_set_updated_data({"flStatus": [1024, 1024, 1024, 1024]})
    assert coord.data["flStatus"] == [1024, 1024, 1024, 1024]

    # New v4 status frame omits flStatus → the merge must carry it forward.
    v4_status = load_fixture("status_v4_revb")
    assert "flStatus" not in v4_status
    await coord._on_status_frame(v4_status)  # noqa: SLF001

    assert coord.data["flStatus"] == [1024, 1024, 1024, 1024]
    assert coord.data["currentScreen"] == 0  # rest of the new frame applied


async def test_status_merge_replaces_flStatus_when_present(
    hass: HomeAssistant, config_entry: MockConfigEntry, load_fixture
) -> None:
    """v3.4 firmware does include flStatus in /api/status — when present,
    the new value must win over whatever the coordinator had cached."""
    client = _make_mock_client(load_fixture("settings_v3_4_revb"))
    coord = BtclockCoordinator(hass, config_entry, client)
    coord.async_set_updated_data({"flStatus": [0, 0, 0, 0]})

    v3_status = load_fixture("status_v3_4_revb")
    assert "flStatus" in v3_status
    await coord._on_status_frame(v3_status)  # noqa: SLF001

    assert coord.data["flStatus"] == v3_status["flStatus"]
