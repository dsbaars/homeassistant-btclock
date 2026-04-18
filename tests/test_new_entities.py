"""Spot-checks for the sensors/switches added/changed in this iteration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.btclock.api import BtclockClient
from custom_components.btclock.const import DOMAIN
from custom_components.btclock.models import ApiVariant


async def _setup(hass: HomeAssistant, settings: dict, status: dict) -> str:
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
    return entry.entry_id


async def test_nostr_relay_sensor_exposes_url_and_connection(
    hass: HomeAssistant, load_fixture
) -> None:
    status = load_fixture("status_v3_4_revb").copy()
    status["connectionStatus"] = {
        "price": False,
        "blocks": False,
        "V2": False,
        "nostr": True,
    }
    await _setup(hass, load_fixture("settings_v3_4_revb"), status)

    state = hass.states.get("sensor.btclock_9d5530_nostr_relay")
    assert state is not None
    assert state.state == "wss://relay.primal.net"
    assert state.attributes.get("connected") is True


async def test_ota_state_sensor_reports_idle_or_updating(
    hass: HomeAssistant, load_fixture
) -> None:
    status = load_fixture("status_v3_4_revb").copy()
    status["isOTAUpdating"] = False
    await _setup(hass, load_fixture("settings_v3_4_revb"), status)

    state = hass.states.get("sensor.btclock_9d5530_ota_state")
    assert state is not None
    assert state.state == "idle"


async def test_light_level_sensor_is_not_diagnostic(
    hass: HomeAssistant, load_fixture
) -> None:
    entry_id = await _setup(
        hass,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
    )
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, entry_id)
        if e.unique_id.endswith("_light_level")
    ]
    assert len(entries) == 1
    # entity_category=None means it's a primary (non-diagnostic) entity
    assert entries[0].entity_category is None


async def test_v2_binary_sensor_is_not_diagnostic(
    hass: HomeAssistant, load_fixture
) -> None:
    entry_id = await _setup(
        hass,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
    )
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, entry_id)
        if e.unique_id.endswith("_v2_connected")
    ]
    assert len(entries) == 1
    assert entries[0].entity_category is None


async def test_screen_select_lists_all_screens_enabled_or_not(
    hass: HomeAssistant, load_fixture
) -> None:
    settings = load_fixture("settings_v3_4_revb")
    await _setup(hass, settings, load_fixture("status_v3_4_revb"))

    state = hass.states.get("select.btclock_9d5530_screen")
    assert state is not None
    options = state.attributes["options"]
    # Fixture has screen id=5 "Halving countdown" with enabled=false — must still be offered
    assert "Halving countdown" in options
    assert len(options) == len(settings["screens"])


async def test_settings_switches_appear_with_current_state(
    hass: HomeAssistant, load_fixture
) -> None:
    settings = load_fixture("settings_v3_4_revb")
    await _setup(hass, settings, load_fixture("status_v3_4_revb"))

    assert (
        hass.states.get("switch.btclock_9d5530_nostr_zap_notifications").state == "off"
    )  # fixture value is False
    assert (
        hass.states.get("switch.btclock_9d5530_led_flash_on_nostr_zap").state == "on"
    )  # fixture value is True
    assert hass.states.get("switch.btclock_9d5530_led_flash_on_new_block").state == "on"
    assert (
        hass.states.get("switch.btclock_9d5530_steal_focus_on_new_block").state == "on"
    )


async def test_settings_switch_toggle_calls_patch(
    hass: HomeAssistant, load_fixture
) -> None:
    settings = load_fixture("settings_v3_4_revb")
    await _setup(hass, settings, load_fixture("status_v3_4_revb"))

    with (
        patch.object(
            BtclockClient, "async_patch_settings", new=AsyncMock()
        ) as patch_mock,
        patch.object(
            BtclockClient, "async_load_settings", new=AsyncMock(return_value=settings)
        ),
        patch.object(
            BtclockClient, "async_update_status", new=AsyncMock(return_value={})
        ),
    ):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.btclock_9d5530_nostr_zap_notifications"},
            blocking=True,
        )

    patch_mock.assert_awaited_once_with({"nostrZapNotify": True})
