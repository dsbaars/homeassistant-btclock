"""Firmware Update entity: version check, release notes fallback, install flows."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.btclock.api import BtclockClient
from custom_components.btclock.const import DOMAIN
from custom_components.btclock.models import ApiVariant
from custom_components.btclock.update import (
    _is_real_version,
    _release_notes_from_compare,
    _repo_base_from_release_url,
)


_RELEASE_URL = "https://git.btclock.dev/api/v1/repos/btclock/btclock_v3/releases/latest"
_COMPARE_URL_RE = re.compile(
    r"https://git\.btclock\.dev/api/v1/repos/btclock/btclock_v3/compare/.*"
)


async def _setup(
    hass: HomeAssistant,
    mock_aioresponse,
    settings: dict,
    status: dict,
    *,
    release: dict | None,
    compare: dict | None = None,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=settings["hostname"],
        data={CONF_HOST: settings["hostname"] + ".local"},
    )
    entry.add_to_hass(hass)

    if release is not None:
        mock_aioresponse.get(_RELEASE_URL, payload=release, repeat=True)
    else:
        mock_aioresponse.get(_RELEASE_URL, status=404, repeat=True)
    if compare is not None:
        mock_aioresponse.get(_COMPARE_URL_RE, payload=compare, repeat=True)

    async def _fake_load(self: BtclockClient) -> dict:
        self._settings = dict(settings)  # noqa: SLF001
        self._variant = ApiVariant.V3_4  # noqa: SLF001
        return self._settings  # noqa: SLF001

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


# ---- pure helpers ------------------------------------------------------------


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("3.3.19", True),
        ("3.4.0", True),
        ("v3.4.0", True),
        ("53eb658", False),
        ("", False),
        (None, False),
        ("3.3", False),
    ],
)
def test_is_real_version(tag, expected) -> None:
    assert _is_real_version(tag) is expected


def test_repo_base_from_release_url() -> None:
    assert _repo_base_from_release_url(_RELEASE_URL) == (
        "https://git.btclock.dev/api/v1/repos/btclock/btclock_v3"
    )
    assert _repo_base_from_release_url("https://example.com/foo") is None


def test_release_notes_from_compare_takes_first_line(load_fixture) -> None:
    notes = _release_notes_from_compare(load_fixture("compare_318_319"))
    assert "fix: remove exception-based parsing paths" in notes
    assert "feat: add notifyEventSourceStatus" in notes
    # Subsequent lines of the first commit's multi-line message are dropped.
    assert "ad-hoc try/except" not in notes


# ---- entity behaviour --------------------------------------------------------


async def test_update_entity_reports_latest_version(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    await _setup(
        hass,
        mock_aioresponse,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        release=load_fixture("release_latest"),
        compare=load_fixture("compare_318_319"),
    )
    state = hass.states.get("update.btclock_9d5530_firmware")
    assert state is not None
    assert state.attributes["installed_version"] == "3.4.0"
    assert state.attributes["latest_version"] == "3.3.19"
    assert (
        state.attributes["release_url"]
        == "https://git.btclock.dev/btclock/btclock_v3/releases/tag/3.3.19"
    )


async def test_update_entity_skipped_for_commit_hash(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    settings = load_fixture("settings_v3_4_revb").copy()
    settings["gitTag"] = "53eb658"  # commit hash — dev build
    await _setup(
        hass,
        mock_aioresponse,
        settings,
        load_fixture("status_v3_4_revb"),
        release=load_fixture("release_latest"),
    )
    assert hass.states.get("update.btclock_9d5530_firmware") is None


async def test_install_latest_calls_auto_update(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    await _setup(
        hass,
        mock_aioresponse,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        release=load_fixture("release_latest"),
        compare=load_fixture("compare_318_319"),
    )
    with (
        patch.object(
            BtclockClient, "async_auto_update_firmware", new=AsyncMock()
        ) as mock_auto,
        patch(
            "custom_components.btclock.update.BtclockUpdate._start_install_watchdog",
        ),
    ):
        await hass.services.async_call(
            "update",
            "install",
            {"entity_id": "update.btclock_9d5530_firmware"},
            blocking=True,
        )
    mock_auto.assert_awaited_once()


async def test_install_specific_version_downloads_and_uploads(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    await _setup(
        hass,
        mock_aioresponse,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        release=load_fixture("release_latest"),
        compare=load_fixture("compare_318_319"),
    )
    # Serve an older version's release + its asset binaries.
    tag_url = (
        "https://git.btclock.dev/api/v1/repos/btclock/btclock_v3/releases/tags/3.3.18"
    )
    old_release = load_fixture("release_latest").copy()
    old_release["tag_name"] = "3.3.18"
    mock_aioresponse.get(tag_url, payload=old_release)

    fw_url = (
        "https://git.btclock.dev/btclock/btclock_v3/releases/download/3.3.19/"
        "btclock_rev_b_213epd_firmware.bin"
    )
    fs_url = (
        "https://git.btclock.dev/btclock/btclock_v3/releases/download/3.3.19/"
        "littlefs_8MB.bin"
    )
    mock_aioresponse.get(fw_url, body=b"\xe9FIRMWARE", status=200)
    mock_aioresponse.get(fs_url, body=b"\xe9LITTLEFS", status=200)

    with (
        patch.object(
            BtclockClient, "async_upload_firmware", new=AsyncMock()
        ) as mock_fw,
        patch.object(BtclockClient, "async_upload_webui", new=AsyncMock()) as mock_fs,
        patch.object(
            BtclockClient, "async_auto_update_firmware", new=AsyncMock()
        ) as mock_auto,
        patch(
            "custom_components.btclock.update.BtclockUpdate._start_install_watchdog",
        ),
    ):
        await hass.services.async_call(
            "update",
            "install",
            {
                "entity_id": "update.btclock_9d5530_firmware",
                "version": "3.3.18",
            },
            blocking=True,
        )
    mock_auto.assert_not_called()
    mock_fw.assert_awaited_once()
    mock_fs.assert_awaited_once()
    # Rev B pairs with 8MB littlefs and the _firmware partial image.
    fw_bytes, fw_name = mock_fw.await_args.args
    assert fw_name == "btclock_rev_b_213epd_firmware.bin"
    assert fw_bytes == b"\xe9FIRMWARE"
    _, fs_name = mock_fs.await_args.args
    assert fs_name == "littlefs_8MB.bin"


async def test_install_watchdog_clears_in_progress_on_version_bump(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    """Watchdog should flip `in_progress` False once gitTag changes.

    Mid-install we also simulate an SSE frame arriving with
    `isOTAUpdating=True` (pre-reboot state). The watchdog must clear that
    stale flag itself, otherwise `in_progress` would stay `True` until the
    next fresh SSE frame — which arrives some seconds after reboot.
    """
    settings = load_fixture("settings_v3_4_revb").copy()
    settings["gitTag"] = "3.3.18"
    entry = await _setup(
        hass,
        mock_aioresponse,
        settings,
        load_fixture("status_v3_4_revb"),
        release=load_fixture("release_latest"),
        compare=load_fixture("compare_318_319"),
    )

    # Watchdog simulation:
    #   poll 1 — device still rebooting: return old settings, and simulate
    #            an SSE frame that arrived with isOTAUpdating=True
    #            (last frame before the reboot cut the stream).
    #   poll 2 — device back online with the new gitTag.
    new_settings = settings.copy()
    new_settings["gitTag"] = "3.3.19"
    call_count = {"n": 0}

    async def _fake_load(self: BtclockClient) -> dict:
        call_count["n"] += 1
        if call_count["n"] == 1:
            coord = entry.runtime_data
            coord.async_set_updated_data({**coord.data, "isOTAUpdating": True})
            value = settings
        else:
            value = new_settings
        self._settings = value  # noqa: SLF001
        return value

    with (
        patch.object(BtclockClient, "async_auto_update_firmware", new=AsyncMock()),
        patch.object(BtclockClient, "async_load_settings", _fake_load),
        patch("custom_components.btclock.update._INSTALL_WATCHDOG_POLL", 0),
    ):
        await hass.services.async_call(
            "update",
            "install",
            {"entity_id": "update.btclock_9d5530_firmware"},
            blocking=True,
        )
        # Let the watchdog task run.
        await hass.async_block_till_done()

    state = hass.states.get("update.btclock_9d5530_firmware")
    assert state is not None
    assert state.attributes["in_progress"] is False
    assert state.attributes["installed_version"] == "3.3.19"
    # The stale `isOTAUpdating=True` from the pre-reboot SSE frame must have
    # been cleared, so in_progress doesn't flip back on to True just because
    # SSE hasn't reconnected yet.
    assert entry.runtime_data.data.get("isOTAUpdating") is False


async def test_install_watchdog_times_out(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    """Watchdog gives up after the timeout even if gitTag never changes."""
    entry = await _setup(
        hass,
        mock_aioresponse,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        release=load_fixture("release_latest"),
        compare=load_fixture("compare_318_319"),
    )

    settings_snapshot = load_fixture("settings_v3_4_revb").copy()

    async def _fake_load(self: BtclockClient) -> dict:
        self._settings = settings_snapshot  # noqa: SLF001
        return settings_snapshot

    with (
        patch.object(BtclockClient, "async_auto_update_firmware", new=AsyncMock()),
        patch.object(BtclockClient, "async_load_settings", _fake_load),
        patch("custom_components.btclock.update._INSTALL_WATCHDOG_POLL", 0),
        patch("custom_components.btclock.update._INSTALL_WATCHDOG_TIMEOUT", 0.05),
    ):
        await hass.services.async_call(
            "update",
            "install",
            {"entity_id": "update.btclock_9d5530_firmware"},
            blocking=True,
        )
        await hass.async_block_till_done()

    state = hass.states.get("update.btclock_9d5530_firmware")
    assert state is not None
    assert state.attributes["in_progress"] is False
    _ = entry


async def test_release_notes_fall_back_to_compare_commits(
    hass: HomeAssistant, mock_aioresponse, load_fixture
) -> None:
    """When `body` is empty, release notes come from compare commit messages."""
    entry = await _setup(
        hass,
        mock_aioresponse,
        load_fixture("settings_v3_4_revb"),
        load_fixture("status_v3_4_revb"),
        release=load_fixture("release_latest"),
        compare=load_fixture("compare_318_319"),
    )
    # Reach into the entity to validate `async_release_notes` output. Going
    # via the entity registry is how HA wires this up internally.
    from homeassistant.helpers import entity_registry as er

    entity_id = "update.btclock_9d5530_firmware"
    registry = er.async_get(hass)
    entry_entry = registry.async_get(entity_id)
    assert entry_entry is not None
    platform = hass.data["entity_platform"]  # type: ignore[index]
    # Easiest: look up on the entity component.
    component = hass.data["update"]  # type: ignore[index]
    entity = component.get_entity(entity_id)
    assert entity is not None
    notes = await entity.async_release_notes()
    assert notes is not None
    assert "fix: remove exception-based parsing paths" in notes
    assert "feat: add notifyEventSourceStatus" in notes
    _ = entry  # silence unused-var
    _ = platform
