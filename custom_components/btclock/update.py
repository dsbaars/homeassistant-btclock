"""Firmware Update entity.

Polls the device's configured `gitReleaseUrl` once a day to discover the
latest BTClock release, then surfaces it as a standard HA update entity.
Only instantiated on 3.4.0+ firmware and only when the installed firmware
tag is a real semver release (never for commit-hash / dev builds).

Install path:
  - If the user presses the default Install (or specifies the latest
    version), we POST /api/firmware/auto_update and let the device
    download + flash itself.
  - If the user picks a specific version, we fetch the matching firmware
    + littlefs assets from the release and upload them over
    /upload/firmware and /upload/webui. The device reboots after the
    second upload.
"""

from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from . import BtclockConfigEntry
from .const import DOMAIN, LOGGER
from .coordinator import BtclockCoordinator
from .entity import BtclockEntity
from .models import ApiVariant

# Map the `hwRev` reported by the device (e.g. "REV_B_EPD_2_13") to the
# PlatformIO env name used as the release-asset prefix. Keep in sync with
# platformio.ini in the firmware repo.
_HW_ASSET_PREFIX: dict[str, str] = {
    "REV_A_EPD_2_13": "lolin_s3_mini_213epd",
    "REV_A_EPD_2_9": "lolin_s3_mini_29epd",
    "REV_B_EPD_2_13": "btclock_rev_b_213epd",
    "REV_B_EPD_2_9": "btclock_rev_b_29epd",
    "REV_V8_EPD_2_13": "btclock_v8_213epd",
}

# LittleFS partition size per hardware family. Mirrors partition_*.csv in the
# firmware repo — lolin_s3_mini=4MB, btclock_rev_b=8MB, btclock_v8=16MB.
_LITTLEFS_SIZE: dict[str, str] = {
    "REV_A_EPD_2_13": "4MB",
    "REV_A_EPD_2_9": "4MB",
    "REV_B_EPD_2_13": "8MB",
    "REV_B_EPD_2_9": "8MB",
    "REV_V8_EPD_2_13": "16MB",
}

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_UPDATE_CHECK_INTERVAL = timedelta(hours=24)
_RELEASE_FETCH_TIMEOUT = 15
_BINARY_FETCH_TIMEOUT = 120


def _is_real_version(tag: str | None) -> bool:
    """Only semver tags like '3.3.19' count — skip commit hashes and '.dev' builds."""
    if not tag:
        return False
    return _SEMVER_RE.match(tag.lstrip("v")) is not None


def _repo_base_from_release_url(url: str) -> str | None:
    """Strip '/releases/latest' (or any trailing segment) off gitReleaseUrl.

    Returns the `/api/v1/repos/<owner>/<repo>` prefix so we can build the
    `/compare/...` and `/releases/tags/...` URLs alongside it.
    """
    match = re.match(r"^(.*?/api/v1/repos/[^/]+/[^/]+)/releases/.*$", url or "")
    return match.group(1) if match else None


def _release_notes_from_compare(compare: dict[str, Any]) -> str:
    """Build a bullet list of first-line commit messages from a compare response."""
    lines: list[str] = []
    for commit in compare.get("commits") or []:
        msg = (commit.get("commit") or {}).get("message") or ""
        first = msg.splitlines()[0].strip() if msg else ""
        if first:
            lines.append(f"- {first}")
    return "\n".join(lines)


class BtclockUpdateCoordinator(DataUpdateCoordinator[dict[str, Any] | None]):
    """Polls the Forgejo releases API once a day.

    Kept separate from the main device coordinator so release checks don't
    interfere with status polling cadence — they run on a 24h timer instead
    of every few seconds.
    """

    def __init__(self, hass: HomeAssistant, device: BtclockCoordinator) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}-release:{device.client.host}",
            config_entry=device.config_entry,
            update_interval=_UPDATE_CHECK_INTERVAL,
        )
        self._device = device
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> dict[str, Any] | None:
        release_url = self._device.client.settings.get("gitReleaseUrl")
        if not release_url:
            return None
        try:
            async with asyncio.timeout(_RELEASE_FETCH_TIMEOUT):
                async with self._session.get(release_url) as resp:
                    if resp.status >= 400:
                        return None
                    release = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(str(err)) from err

        # BTClock releases routinely ship with an empty `body`. Fall back to
        # a synthesized changelog from the compare API so the user actually
        # sees what's in the update.
        body = (release.get("body") or "").strip()
        installed = self._device.client.settings.get("gitTag") or ""
        latest = release.get("tag_name") or ""
        if (
            not body
            and _is_real_version(installed)
            and _is_real_version(latest)
            and installed.lstrip("v") != latest.lstrip("v")
        ):
            repo_base = _repo_base_from_release_url(release_url)
            if repo_base:
                compare_url = f"{repo_base}/compare/{installed}...{latest}"
                try:
                    async with asyncio.timeout(_RELEASE_FETCH_TIMEOUT):
                        async with self._session.get(compare_url) as resp:
                            if resp.status < 400:
                                release["_compare"] = await resp.json()
                except (aiohttp.ClientError, TimeoutError):
                    # Keep the release data without the synthesized changelog.
                    pass
        return release


class BtclockUpdate(BtclockEntity, UpdateEntity):
    """Surfaces the device's installed firmware vs latest release."""

    # Not coordinated by the main status coordinator alone — we also listen
    # to the release coordinator for latest_version changes.
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_translation_key = "firmware"
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.SPECIFIC_VERSION
        | UpdateEntityFeature.RELEASE_NOTES
        | UpdateEntityFeature.PROGRESS
    )

    def __init__(
        self,
        device: BtclockCoordinator,
        release_coordinator: BtclockUpdateCoordinator,
    ) -> None:
        super().__init__(device)
        self._release = release_coordinator
        self._attr_unique_id = f"{device.config_entry.entry_id}_firmware"

    async def async_added_to_hass(self) -> None:
        """Subscribe to both the device coordinator and the release coordinator."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._release.async_add_listener(self.async_write_ha_state)
        )

    @property
    def installed_version(self) -> str | None:
        tag = self.coordinator.client.settings.get("gitTag")
        return tag if _is_real_version(tag) else None

    @property
    def latest_version(self) -> str | None:
        release = self._release.data or {}
        tag = release.get("tag_name")
        return tag if _is_real_version(tag) else None

    @property
    def release_url(self) -> str | None:
        release = self._release.data or {}
        return release.get("html_url") or None

    @property
    def in_progress(self) -> bool:
        return bool(self.coordinator.data.get("isOTAUpdating"))

    async def async_release_notes(self) -> str | None:
        release = self._release.data or {}
        body = (release.get("body") or "").strip()
        if body:
            return body
        compare = release.get("_compare") or {}
        notes = _release_notes_from_compare(compare)
        return notes or None

    async def async_install(self, version: str | None, backup: bool, **_: Any) -> None:
        client = self.coordinator.client
        release = self._release.data or {}
        latest = release.get("tag_name")

        # Default (version is None) or installing the latest: let the device
        # do the work. One POST, one reboot — no bytes over the HA session.
        if version is None or version == latest:
            await client.async_auto_update_firmware()
            await self.coordinator.async_request_refresh()
            return

        # Targeted version install — we have to upload the matching binaries
        # ourselves. Bail early if we can't map the hardware.
        hw_rev = (client.settings.get("hwRev") or "").upper()
        prefix = _HW_ASSET_PREFIX.get(hw_rev)
        fs_size = _LITTLEFS_SIZE.get(hw_rev)
        if not prefix or not fs_size:
            raise HomeAssistantError(
                f"Unsupported hardware for targeted install: {hw_rev}"
            )

        repo_base = _repo_base_from_release_url(
            client.settings.get("gitReleaseUrl") or ""
        )
        if not repo_base:
            raise HomeAssistantError("gitReleaseUrl is not set on the device")

        session = async_get_clientsession(self.hass)
        tag_url = f"{repo_base}/releases/tags/{version}"
        try:
            async with asyncio.timeout(_RELEASE_FETCH_TIMEOUT):
                async with session.get(tag_url) as resp:
                    if resp.status >= 400:
                        raise HomeAssistantError(
                            f"Release {version} not found at {tag_url}"
                        )
                    target = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(
                f"Failed to fetch release {version}: {err}"
            ) from err

        assets = {
            a.get("name"): a.get("browser_download_url")
            for a in (target.get("assets") or [])
            if a.get("name") and a.get("browser_download_url")
        }
        firmware_name = f"{prefix}_firmware.bin"
        littlefs_name = f"littlefs_{fs_size}.bin"
        firmware_url = assets.get(firmware_name)
        littlefs_url = assets.get(littlefs_name)
        if not firmware_url:
            raise HomeAssistantError(f"Release {version} is missing {firmware_name}")

        async def _fetch_bytes(url: str) -> bytes:
            async with asyncio.timeout(_BINARY_FETCH_TIMEOUT):
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    return await resp.read()

        firmware_bytes = await _fetch_bytes(firmware_url)
        await client.async_upload_firmware(firmware_bytes, firmware_name)

        # Upload webui last — the firmware's upload handler restarts the
        # device after `Update.end()` on the final segment, so once this
        # finishes the BTClock reboots into the new image.
        if littlefs_url:
            littlefs_bytes = await _fetch_bytes(littlefs_url)
            await client.async_upload_webui(littlefs_bytes, littlefs_name)

        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BtclockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one Update entity per BTClock running a real release."""
    device = entry.runtime_data
    if device.client.variant is not ApiVariant.V3_4:
        return
    installed = device.client.settings.get("gitTag")
    if not _is_real_version(installed):
        LOGGER.debug(
            "Skipping Update entity for %s — gitTag %r is a dev build",
            device.client.host,
            installed,
        )
        return

    release_coordinator = BtclockUpdateCoordinator(hass, device)
    # Don't block setup on the release check — if git.btclock.dev is slow or
    # unreachable the rest of the integration should still come up. The
    # entity will just report `latest_version = None` until the next tick.
    await release_coordinator.async_refresh()

    async_add_entities([BtclockUpdate(device, release_coordinator)])
