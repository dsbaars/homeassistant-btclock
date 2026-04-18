"""Price/blocks feed connectivity must follow the active dataSource."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.btclock.api import BtclockClient
from custom_components.btclock.const import DOMAIN
from custom_components.btclock.models import ApiVariant, DataSource


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


@pytest.mark.parametrize(
    "data_source, connection_status, expect_price, expect_blocks",
    [
        # BTCLOCK / CUSTOM route via the V2 relay, so V2 is the ground truth
        (
            DataSource.BTCLOCK,
            {"V2": True, "price": False, "blocks": False, "nostr": False},
            True,
            True,
        ),
        (
            DataSource.BTCLOCK,
            {"V2": False, "price": True, "blocks": True, "nostr": True},
            False,
            False,
        ),
        (
            DataSource.CUSTOM,
            {"V2": True, "price": False, "blocks": False, "nostr": False},
            True,
            True,
        ),
        # THIRD_PARTY → Kraken for price + mempool for blocks
        (
            DataSource.THIRD_PARTY,
            {"V2": False, "price": True, "blocks": False, "nostr": False},
            True,
            False,
        ),
        (
            DataSource.THIRD_PARTY,
            {"V2": True, "price": False, "blocks": True, "nostr": True},
            False,
            True,
        ),
        # NOSTR pool covers both
        (
            DataSource.NOSTR,
            {"V2": False, "price": False, "blocks": False, "nostr": True},
            True,
            True,
        ),
        (
            DataSource.NOSTR,
            {"V2": True, "price": True, "blocks": True, "nostr": False},
            False,
            False,
        ),
    ],
)
async def test_price_blocks_feed_follows_datasource(
    hass: HomeAssistant,
    load_fixture,
    data_source: DataSource,
    connection_status: dict,
    expect_price: bool,
    expect_blocks: bool,
) -> None:
    settings = load_fixture("settings_v3_4_revb").copy()
    settings["dataSource"] = int(data_source)
    status = load_fixture("status_v3_4_revb").copy()
    status["connectionStatus"] = connection_status

    await _setup(hass, settings, status)

    price = hass.states.get("binary_sensor.btclock_9d5530_price_feed")
    blocks = hass.states.get("binary_sensor.btclock_9d5530_blocks_feed")
    assert price is not None
    assert blocks is not None
    assert (price.state == "on") is expect_price, (
        f"dataSource={data_source} {connection_status}"
    )
    assert (blocks.state == "on") is expect_blocks, (
        f"dataSource={data_source} {connection_status}"
    )
