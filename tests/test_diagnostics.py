"""Diagnostics download: sensitive settings must be redacted."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.components.diagnostics import REDACTED
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.btclock.api import BtclockClient
from custom_components.btclock.const import DOMAIN
from custom_components.btclock.diagnostics import async_get_config_entry_diagnostics
from custom_components.btclock.models import ApiVariant


async def _setup(
    hass: HomeAssistant,
    mock_aioresponse,
    settings: dict,
    status: dict,
    *,
    variant: ApiVariant,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=settings["hostname"],
        data={CONF_HOST: settings["hostname"] + ".local"},
    )
    entry.add_to_hass(hass)

    if release_url := settings.get("gitReleaseUrl"):
        mock_aioresponse.get(release_url, status=404, repeat=True)

    async def _fake_load(self: BtclockClient) -> dict:
        self._settings = dict(settings)  # noqa: SLF001
        self._variant = variant  # noqa: SLF001
        return self._settings  # noqa: SLF001

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
    return entry


async def test_diagnostics_redacts_v4_sensitive_settings(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    entry = await _setup(
        hass,
        mock_aioresponse,
        load_fixture("settings_v4_revb"),
        load_fixture("status_v4_revb"),
        variant=ApiVariant.V4,
    )
    diag = await async_get_config_entry_diagnostics(hass, entry)

    settings = diag["settings"]
    # New v4 sensitive fields must be scrubbed.
    for key in ("wifiMac", "nostrZapPubkeys", "nwcUriMasked", "nostrPubKey", "ip"):
        assert settings[key] == REDACTED, f"{key} was not redacted"
    # Non-sensitive operational data is preserved.
    assert settings["numScreens"] == 7
    assert settings["availablePools"] == ["noderunners", "ocean", "braiins"]
    assert diag["variant"] == "v4"
