"""v4-only entity gating: mining-pool / font selects, diagnostic buttons,
v4 setting switches, v4 number sliders. v3.4 setups must NOT see them."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.btclock.api import BtclockClient, BtclockError
from custom_components.btclock.const import DOMAIN
from custom_components.btclock.models import ApiVariant


async def _setup(
    hass: HomeAssistant,
    mock_aioresponse,
    settings: dict,
    status: dict,
    *,
    variant: ApiVariant,
) -> str:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=settings["hostname"],
        data={CONF_HOST: settings["hostname"] + ".local"},
    )
    entry.add_to_hass(hass)

    # The Update entity fires off a release fetch — stub it so we don't
    # hit the network. Tests don't assert on update behaviour.
    if release_url := settings.get("gitReleaseUrl"):
        mock_aioresponse.get(release_url, status=404, repeat=True)

    async def _fake_load(self: BtclockClient) -> dict:
        self._settings = settings  # noqa: SLF001
        self._variant = variant  # noqa: SLF001
        return settings

    with (
        patch.object(BtclockClient, "async_load_settings", _fake_load),
        patch.object(
            BtclockClient, "async_update_status", new=AsyncMock(return_value=status)
        ),
        patch.object(
            BtclockClient,
            "async_get_frontlight_status",
            new=AsyncMock(return_value={"flStatus": [1024] * 7}),
        ),
        patch(
            "custom_components.btclock.coordinator.BtclockCoordinator.async_start",
            new=AsyncMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry.entry_id


# ---- selects --------------------------------------------------------------


async def test_mining_pool_select_appears_on_v4_with_real_catalog(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    await _setup(
        hass,
        mock_aioresponse,
        load_fixture("settings_v4_revb"),
        load_fixture("status_v4_revb"),
        variant=ApiVariant.V4,
    )
    state = hass.states.get("select.btclock_v4abcd_mining_pool")
    assert state is not None
    assert state.state == "noderunners"
    assert "ocean" in state.attributes["options"]


async def test_font_select_appears_on_v4_with_real_catalog(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    settings = load_fixture("settings_v4_revb").copy()
    settings["fontName"] = "antonio"
    await _setup(
        hass,
        mock_aioresponse,
        settings,
        load_fixture("status_v4_revb"),
        variant=ApiVariant.V4,
    )
    state = hass.states.get("select.btclock_v4abcd_display_font")
    assert state is not None
    assert state.state == "antonio"


async def test_mining_pool_and_font_selects_absent_on_v3_4(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    """v3.4 fixture's `availablePools` is `[""]` (placeholder) — no select."""
    await _setup(
        hass,
        mock_aioresponse,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        variant=ApiVariant.V3_4,
    )
    assert hass.states.get("select.btclock_9d5530_mining_pool") is None
    assert hass.states.get("select.btclock_9d5530_display_font") is None


# ---- buttons --------------------------------------------------------------


async def test_v4_diagnostic_buttons_appear_on_v4(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    await _setup(
        hass,
        mock_aioresponse,
        load_fixture("settings_v4_revb"),
        load_fixture("status_v4_revb"),
        variant=ApiVariant.V4,
    )
    assert hass.states.get("button.btclock_v4abcd_simulate_nostr_zap") is not None
    assert hass.states.get("button.btclock_v4abcd_clear_cached_pool_logos") is not None
    assert hass.states.get("button.btclock_v4abcd_restart_data_sources") is not None


async def test_v4_diagnostic_buttons_absent_on_v3_4(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    await _setup(
        hass,
        mock_aioresponse,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        variant=ApiVariant.V3_4,
    )
    # The v4-only path-table keys aren't in V3_4_PATHS, so button.py's
    # path-key filter drops them automatically.
    assert hass.states.get("button.btclock_9d5530_simulate_nostr_zap") is None
    assert hass.states.get("button.btclock_9d5530_clear_cached_pool_logos") is None
    assert hass.states.get("button.btclock_9d5530_restart_data_sources") is None


# ---- switches -------------------------------------------------------------


async def test_v4_settings_switches_appear_when_settings_present(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    await _setup(
        hass,
        mock_aioresponse,
        load_fixture("settings_v4_revb"),
        load_fixture("status_v4_revb"),
        variant=ApiVariant.V4,
    )
    assert hass.states.get("switch.btclock_v4abcd_mining_pool_stats") is not None
    assert hass.states.get("switch.btclock_v4abcd_show_pool_wide_stats") is not None
    # `bitaxeEnabled` is missing from this fixture — no switch.
    assert hass.states.get("switch.btclock_v4abcd_bitaxe_data_source") is None


async def test_v4_settings_switches_absent_on_v3_4(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    await _setup(
        hass,
        mock_aioresponse,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        variant=ApiVariant.V3_4,
    )
    # v3.4 fixture has none of the v4-specific setting keys.
    for key in (
        "mining_pool_stats",
        "show_pool_wide_stats",
        "bitaxe_data_source",
        "mow_mode",
        "use_sats_symbol",
        "hide_leading_zero_on_hours",
    ):
        assert hass.states.get(f"switch.btclock_9d5530_{key}") is None


# ---- numbers --------------------------------------------------------------


async def test_v4_number_entities_absent_when_setting_missing(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    """The v3.4 fixture must not produce v4-only number entities."""
    await _setup(
        hass,
        mock_aioresponse,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        variant=ApiVariant.V3_4,
    )
    assert hass.states.get("number.btclock_9d5530_bitaxe_poll_interval") is None
    assert hass.states.get("number.btclock_9d5530_mining_pool_poll_interval") is None
    # The always-present LED brightness number is unaffected.
    assert hass.states.get("number.btclock_9d5530_led_brightness") is not None


async def test_v4_pool_poll_sec_appears_when_setting_present(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    settings = load_fixture("settings_v4_revb").copy()
    settings["poolPollSec"] = 60
    settings["bitaxePollSec"] = 10
    settings["fullRefreshMin"] = 60
    await _setup(
        hass,
        mock_aioresponse,
        settings,
        load_fixture("status_v4_revb"),
        variant=ApiVariant.V4,
    )
    assert (
        hass.states.get("number.btclock_v4abcd_mining_pool_poll_interval") is not None
    )
    assert hass.states.get("number.btclock_v4abcd_bitaxe_poll_interval") is not None
    assert hass.states.get("number.btclock_v4abcd_full_refresh_interval") is not None


# ---- API client gating ----------------------------------------------------


async def test_simulate_zap_on_v3_4_raises() -> None:
    """The v4-only client method must refuse on v3.4 firmware so the
    integration never tries to POST a path the device wouldn't route."""
    client = BtclockClient(host="x", session=AsyncMock(), username=None, password=None)
    client._variant = ApiVariant.V3_4  # noqa: SLF001
    with pytest.raises(BtclockError):
        await client.async_simulate_zap()
