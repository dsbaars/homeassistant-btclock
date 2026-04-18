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
    hass: HomeAssistant, settings: dict, status: dict, variant: ApiVariant
) -> MockConfigEntry:
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
    "settings_fixture, variant, expect_buttons, expect_frontlight",
    [
        ("settings_v3_4_revb", ApiVariant.V3_4, True, True),
        ("settings_v3_4_reva", ApiVariant.V3_4, True, False),
        ("settings_legacy", ApiVariant.LEGACY, False, False),
    ],
)
async def test_entity_composition_by_variant(
    hass: HomeAssistant,
    load_fixture,
    settings_fixture: str,
    variant: ApiVariant,
    expect_buttons: bool,
    expect_frontlight: bool,
) -> None:
    settings = load_fixture(settings_fixture)
    status = (
        load_fixture("status_legacy")
        if variant is ApiVariant.LEGACY
        else load_fixture("status_v3_4_revb")
    )
    entry = await _setup(hass, settings, status, variant)

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    domains = {e.entity_id.split(".")[0] for e in entities}
    assert {"sensor", "binary_sensor", "switch", "select", "light"} <= domains
    assert ("button" in domains) is expect_buttons

    frontlight_present = any(e.unique_id.endswith("_frontlight") for e in entities)
    assert frontlight_present is expect_frontlight

    await hass.config_entries.async_unload(entry.entry_id)
