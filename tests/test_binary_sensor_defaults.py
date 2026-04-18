"""V2/nostr sensors should auto-enable when those feeds are live at setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.btclock.api import BtclockClient
from custom_components.btclock.const import DOMAIN
from custom_components.btclock.models import ApiVariant


async def _setup_with_status(hass: HomeAssistant, settings: dict, status: dict) -> str:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="btclock-x", data={CONF_HOST: "x.local"}
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
            "custom_components.btclock.coordinator.BtclockCoordinator.async_start_push",
            new=AsyncMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry.entry_id


@pytest.mark.parametrize(
    "connection_status, expect_enabled",
    [
        # Mempool feed: V2/nostr hidden. price/blocks always enabled (they're
        # the common default); we never hide them just because they're idle.
        (
            {"price": True, "blocks": True, "V2": False, "nostr": False},
            {
                "v2_connected": False,
                "nostr_connected": False,
                "price_connected": True,
                "blocks_connected": True,
            },
        ),
        # Live production device using V2+nostr: those auto-enable;
        # price/blocks stay enabled-by-default (user may toggle dataSource later).
        (
            {"price": False, "blocks": False, "V2": True, "nostr": True},
            {
                "v2_connected": True,
                "nostr_connected": True,
                "price_connected": True,
                "blocks_connected": True,
            },
        ),
        # Only nostr active — V2 stays hidden.
        (
            {"price": False, "blocks": False, "V2": False, "nostr": True},
            {
                "v2_connected": False,
                "nostr_connected": True,
                "price_connected": True,
                "blocks_connected": True,
            },
        ),
    ],
)
async def test_connectivity_defaults_follow_live_connection_status(
    hass: HomeAssistant,
    load_fixture,
    connection_status: dict,
    expect_enabled: dict,
) -> None:
    status = load_fixture("status_v3_4_revb").copy()
    status["connectionStatus"] = connection_status

    entry_id = await _setup_with_status(
        hass, load_fixture("settings_v3_4_revb"), status
    )

    registry = er.async_get(hass)
    for desc_key, should_be_enabled in expect_enabled.items():
        entries = [
            e
            for e in er.async_entries_for_config_entry(registry, entry_id)
            if e.unique_id.endswith(f"_{desc_key}")
        ]
        assert len(entries) == 1, f"expected one {desc_key} entity"
        entity = entries[0]
        is_disabled = entity.disabled_by is not None
        assert is_disabled is not should_be_enabled, (
            f"{desc_key}: disabled={is_disabled}, "
            f"expected_enabled={should_be_enabled}, feed={connection_status}"
        )
