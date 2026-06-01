"""End-to-end setup: confirm entity composition differs by firmware variant."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
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
    variant: ApiVariant,
    mock_aioresponse,
) -> MockConfigEntry:
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

    return entry


@pytest.mark.parametrize(
    "settings_fixture, variant, expected_button_keys, expect_frontlight",
    [
        (
            "settings_v3_4_revb",
            ApiVariant.V3_4,
            {
                "identify",
                "restart",
                "full_refresh",
                "screen_next",
                "screen_previous",
                "frontlight_flash",
            },
            True,
        ),
        (
            "settings_v3_4_reva",
            ApiVariant.V3_4,
            {"identify", "restart", "full_refresh", "screen_next", "screen_previous"},
            False,
        ),
        (
            "settings_legacy",
            ApiVariant.LEGACY,
            {"identify", "restart", "full_refresh"},
            False,
        ),
    ],
)
async def test_entity_composition_by_variant(
    hass: HomeAssistant,
    load_fixture,
    mock_aioresponse,
    settings_fixture: str,
    variant: ApiVariant,
    expected_button_keys: set[str],
    expect_frontlight: bool,
) -> None:
    settings = load_fixture(settings_fixture)
    status = (
        load_fixture("status_legacy")
        if variant is ApiVariant.LEGACY
        else load_fixture("status_v3_4_revb")
    )
    entry = await _setup(hass, settings, status, variant, mock_aioresponse)

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    domains = {e.entity_id.split(".")[0] for e in entities}
    assert {"sensor", "binary_sensor", "switch", "select", "light"} <= domains

    button_keys = {
        e.unique_id.removeprefix(f"{entry.entry_id}_")
        for e in entities
        if e.entity_id.startswith("button.")
    }
    assert button_keys == expected_button_keys

    frontlight_present = any(e.unique_id.endswith("_frontlight") for e in entities)
    assert frontlight_present is expect_frontlight

    await hass.config_entries.async_unload(entry.entry_id)


# Unique-id suffixes (entity description `key`s) for entities that only exist
# on v4 firmware. None of these may appear on legacy (3.3.x) or 3.4.0 setups —
# this is the guard that the v4 additions stay fully gated and don't break,
# 404, or clutter older devices.
_V4_ONLY_KEYS = frozenset(
    {
        # selects
        "font",
        "price_symbol",
        "mining_pool",
        # switches
        "nwc_enabled",
        "nwc_show_notify",
        "nwc_flash_on_pay",
        "decimal_share_dot",
        "mining_pool_stats",
        "pool_global_stats",
        # numbers
        "nwc_refresh_sec",
        "bitaxe_poll_sec",
        "pool_poll_sec",
        # binary sensor / sensor
        "nwc_connected",
        "wifi_mac",
        # buttons
        "stop_datasources",
        "restart_datasources",
        "simulate_zap",
        "clear_pool_logos",
    }
)


@pytest.mark.parametrize(
    "settings_fixture, variant",
    [
        ("settings_legacy", ApiVariant.LEGACY),
        ("settings_v3_4_revb", ApiVariant.V3_4),
    ],
)
async def test_v4_only_entities_absent_on_older_firmware(
    hass: HomeAssistant,
    load_fixture,
    mock_aioresponse,
    settings_fixture: str,
    variant: ApiVariant,
) -> None:
    """Legacy (3.3.x) and 3.4.0 setups must never spawn a v4-only entity."""
    settings = load_fixture(settings_fixture)
    status = (
        load_fixture("status_legacy")
        if variant is ApiVariant.LEGACY
        else load_fixture("status_v3_4_revb")
    )
    entry = await _setup(hass, settings, status, variant, mock_aioresponse)

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    suffixes = {e.unique_id.removeprefix(f"{entry.entry_id}_") for e in entities}
    leaked = suffixes & _V4_ONLY_KEYS
    assert not leaked, f"{variant} leaked v4-only entities: {sorted(leaked)}"

    # The currency *select* is 3.4.0+ (POST /api/show/currency) — present on
    # 3.4.0, but must be absent on legacy GET-only firmware. (The currency
    # *sensor* shares the `_currency` suffix and exists on every variant, so
    # gate this on the select domain.)
    if variant is ApiVariant.LEGACY:
        currency_selects = [
            e
            for e in entities
            if e.domain == "select" and e.unique_id.endswith("_currency")
        ]
        assert not currency_selects

    await hass.config_entries.async_unload(entry.entry_id)
