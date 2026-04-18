"""Async HTTP client for the BTClock device.

Speaks both the legacy (≤3.3.x, GET-based) and 3.4.0+ (POST-based) REST
surfaces. The variant is detected from `GET /api/settings` and cached on the
client; callers should re-invoke `async_detect_variant()` whenever the device
is known to have rebooted (e.g. after a reconnect).
"""

from __future__ import annotations

import asyncio
import socket
from typing import Any

import aiohttp

from .api_paths import PATHS
from .const import LOGGER, REQUEST_TIMEOUT
from .models import ApiVariant, LedDict, Settings, Status, SystemStatus

# Build timestamp at which firmware flipped to POST-style state changes.
# Reviewed against /Users/padjuri/src/btclock_v3_fci/platformio.ini + scripts/git_rev.py
# — we'll refine once 3.4.0 is tagged, for now "anything built after this
# cutoff or tagged 3.4+" counts as new.
_V3_4_BUILD_CUTOFF = (
    1_735_689_600  # 2025-01-01 UTC; 3.4.0 branch started long after this
)


class BtclockError(Exception):
    """Base exception for API errors."""


class BtclockCommunicationError(BtclockError):
    """Raised on connection/timeout errors."""


class BtclockAuthError(BtclockError):
    """Raised on 401/403 — triggers the HA reauth flow."""


class BtclockClient:
    """Async client for one BTClock device."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        *,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._host = host
        self._session = session
        self._auth = (
            aiohttp.BasicAuth(username, password) if username is not None else None
        )
        self._variant: ApiVariant | None = None
        self._settings: Settings | None = None
        self._status: Status | None = None

    # ---- Connection / identity --------------------------------------------------

    @property
    def host(self) -> str:
        return self._host

    @property
    def variant(self) -> ApiVariant:
        if self._variant is None:
            raise RuntimeError("Call async_load_settings() before accessing variant")
        return self._variant

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            raise RuntimeError("Call async_load_settings() first")
        return self._settings

    @property
    def status(self) -> Status | None:
        return self._status

    @property
    def has_auth(self) -> bool:
        return self._auth is not None

    @property
    def session(self) -> aiohttp.ClientSession:
        return self._session

    @property
    def auth(self) -> aiohttp.BasicAuth | None:
        return self._auth

    def set_credentials(self, username: str | None, password: str | None) -> None:
        """Replace the stored credentials (used on reauth)."""
        self._auth = (
            aiohttp.BasicAuth(username, password) if username is not None else None
        )

    # ---- Variant detection ------------------------------------------------------

    async def async_load_settings(self) -> Settings:
        """Fetch /api/settings and update the cached variant + settings."""
        data = await self._request_key("settings_get")
        self._settings = data or {}
        self._variant = detect_variant(self._settings)
        return self._settings

    # ---- Status / system --------------------------------------------------------

    async def async_update_status(self) -> Status:
        data = await self._request_key("status")
        self._status = data or {}
        return self._status

    async def async_get_system_status(self) -> SystemStatus:
        return await self._request_key("system_status") or {}

    async def async_patch_settings(self, patch: dict[str, Any]) -> None:
        """PATCH a partial settings update.

        Both variants use the same body shape; only the path differs. Callers
        should follow up with `async_load_settings()` so cached settings stay
        in sync with what the device just accepted.
        """
        await self._request_key("settings_patch", json_body=patch, expect_json=False)

    # ---- Screen / timer control -------------------------------------------------

    async def async_timer_start(self) -> None:
        await self._request_key("timer_start", expect_json=False)

    async def async_timer_stop(self) -> None:
        await self._request_key("timer_pause", expect_json=False)

    async def async_set_screen(self, screen_id: int) -> None:
        if self.variant is ApiVariant.V3_4:
            await self._request_key(
                "show_screen", params={"s": screen_id}, expect_json=False
            )
        else:
            await self._request_key("show_screen", fmt=(screen_id,), expect_json=False)

    async def async_screen_next(self) -> None:
        self._require_v3_4("screen_next")
        await self._request_key("screen_next", expect_json=False)

    async def async_screen_previous(self) -> None:
        self._require_v3_4("screen_prev")
        await self._request_key("screen_prev", expect_json=False)

    async def async_set_currency(self, code: str) -> None:
        self._require_v3_4("show_currency")
        await self._request_key("show_currency", params={"c": code}, expect_json=False)

    async def async_show_text(self, text: str) -> None:
        """Display `text` across all screens, one character per screen."""
        self._require_v3_4("show_text")
        await self._request_key("show_text", params={"t": text}, expect_json=False)

    async def async_show_custom(self, screens: list[str]) -> None:
        """Display one string per screen (array body, clamped to numScreens)."""
        self._require_v3_4("show_custom")
        await self._request_key("show_custom", json_body=screens, expect_json=False)

    # ---- LEDs -------------------------------------------------------------------

    async def async_get_lights(self) -> list[LedDict]:
        return await self._request_key("lights_get") or []

    async def async_set_lights(self, leds: list[LedDict]) -> None:
        """Write the full LED array. Length must match device count."""
        await self._request_key("lights_set", json_body=leds, expect_json=False)

    async def async_lights_off(self) -> None:
        await self._request_key("lights_off", expect_json=False)

    # ---- Actions (3.4.0 only) ---------------------------------------------------

    async def async_identify(self) -> None:
        self._require_v3_4("identify")
        await self._request_key("identify", expect_json=False)

    async def async_restart(self) -> None:
        self._require_v3_4("restart")
        await self._request_key("restart", expect_json=False)

    async def async_full_refresh(self) -> None:
        self._require_v3_4("full_refresh")
        await self._request_key("full_refresh", expect_json=False)

    # ---- DND --------------------------------------------------------------------

    async def async_dnd_enable(self) -> None:
        self._require_v3_4("dnd_enable")
        await self._request_key("dnd_enable", expect_json=False)

    async def async_dnd_disable(self) -> None:
        self._require_v3_4("dnd_disable")
        await self._request_key("dnd_disable", expect_json=False)

    # ---- Frontlight (3.4.0 + hasFrontlight) -------------------------------------

    async def async_frontlight_on(self) -> None:
        self._require_v3_4("frontlight_on")
        await self._request_key("frontlight_on", expect_json=False)

    async def async_frontlight_off(self) -> None:
        self._require_v3_4("frontlight_off")
        await self._request_key("frontlight_off", expect_json=False)

    async def async_frontlight_flash(self) -> None:
        self._require_v3_4("frontlight_flash")
        await self._request_key("frontlight_flash", expect_json=False)

    async def async_frontlight_brightness(self, value: int) -> None:
        self._require_v3_4("frontlight_bright")
        await self._request_key(
            "frontlight_bright", params={"b": value}, expect_json=False
        )

    # ---- OTA / firmware update (variant-dispatched) -----------------------------

    async def async_auto_update_firmware(self) -> None:
        """Kick the device's own OTA downloader; it reboots into the new image.

        Legacy firmware serves this over GET; 3.4.0+ over POST — handled by
        the path tables.
        """
        await self._request_key("auto_update", expect_json=False)

    async def async_upload_firmware(self, data: bytes, filename: str) -> None:
        """Multipart upload of the firmware partition image."""
        await self._upload_key("upload_firmware", data, filename, field="firmware")

    async def async_upload_webui(self, data: bytes, filename: str) -> None:
        """Multipart upload of the LittleFS webUI image."""
        await self._upload_key("upload_webui", data, filename, field="webui")

    # ---- Internals --------------------------------------------------------------

    def _require_v3_4(self, key: str) -> None:
        if self._variant is not ApiVariant.V3_4:
            raise BtclockError(f"Endpoint {key!r} requires firmware 3.4.0+")

    def url_for(self, key: str, *fmt: Any) -> str:
        """Resolve a path-table key to an absolute URL, for SSE or tests."""
        variant = self._variant or ApiVariant.V3_4
        _, template = PATHS[variant][key]
        path = template.format(*fmt) if fmt else template
        return f"http://{self._host}{path}"

    async def _request_key(
        self,
        key: str,
        *,
        fmt: tuple[Any, ...] = (),
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        expect_json: bool = True,
    ) -> Any:
        """Resolve a path-table key for the active variant and execute."""
        # If variant isn't known yet, use the legacy table to fetch /api/settings —
        # both firmwares expose GET /api/settings at the same path.
        variant = self._variant or ApiVariant.LEGACY
        try:
            method, template = PATHS[variant][key]
        except KeyError as err:
            raise BtclockError(
                f"Endpoint {key!r} not available on {variant} firmware"
            ) from err
        path = template.format(*fmt) if fmt else template
        url = f"http://{self._host}{path}"
        return await self._request(
            method, url, params=params, json_body=json_body, expect_json=expect_json
        )

    async def _upload_key(
        self, key: str, data: bytes, filename: str, *, field: str
    ) -> None:
        """POST a binary blob to an /upload endpoint as multipart form-data.

        Generous 120s timeout — the device erases + writes the flash partition
        inline during the upload, which can take a while on larger images.
        """
        variant = self._variant or ApiVariant.V3_4
        method, template = PATHS[variant][key]
        url = f"http://{self._host}{template}"
        form = aiohttp.FormData()
        form.add_field(
            field, data, filename=filename, content_type="application/octet-stream"
        )
        try:
            async with asyncio.timeout(120):
                resp = await self._session.request(
                    method, url, data=form, auth=self._auth
                )
                if resp.status in (401, 403):
                    raise BtclockAuthError(f"Authentication required for {url}")
                resp.raise_for_status()
        except TimeoutError as err:
            raise BtclockCommunicationError(f"Timeout uploading to {url}") from err
        except (aiohttp.ClientError, socket.gaierror) as err:
            raise BtclockCommunicationError(f"Error uploading to {url}: {err}") from err

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        expect_json: bool = True,
    ) -> Any:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    auth=self._auth,
                )
                if resp.status in (401, 403):
                    raise BtclockAuthError(f"Authentication required for {url}")
                resp.raise_for_status()
                if not expect_json:
                    return None
                ctype = resp.headers.get("Content-Type", "")
                if "application/json" not in ctype:
                    return None
                return await resp.json()
        except TimeoutError as err:
            raise BtclockCommunicationError(f"Timeout talking to {url}") from err
        except (aiohttp.ClientError, socket.gaierror) as err:
            raise BtclockCommunicationError(f"Error talking to {url}: {err}") from err


def detect_variant(settings: Settings) -> ApiVariant:
    """Pick the firmware variant from a `/api/settings` response.

    Strategy:
      1. `gitTag` is a real semver — trust it. `>= 3.4` → V3_4, else LEGACY.
         (Observed in the wild: 3.3.19 builds from main already expose
         `httpAuthPassSet`, yet still use GET on action routes — so we
         must not let the fallbacks flip those to V3_4.)
      2. No usable tag: `httpAuthPassSet` present → V3_4.
      3. Still unknown: `lastBuildTime` past the 3.4.0 cutoff → V3_4.
      4. Otherwise LEGACY.
    """
    tag = str(settings.get("gitTag") or "").lstrip("v").strip()
    tag_parts = tag.split(".") if tag else []
    try:
        major = int(tag_parts[0]) if tag_parts else None
        minor = int(tag_parts[1]) if len(tag_parts) > 1 else 0
    except ValueError:
        major = minor = None

    if major is not None:
        if (major, minor) >= (3, 4):
            LOGGER.debug("Detected V3_4 via gitTag=%s", tag)
            return ApiVariant.V3_4
        LOGGER.debug("Detected LEGACY via gitTag=%s", tag)
        return ApiVariant.LEGACY

    if "httpAuthPassSet" in settings:
        LOGGER.debug("Detected V3_4 via httpAuthPassSet field")
        return ApiVariant.V3_4

    build = settings.get("lastBuildTime")
    if build:
        try:
            if int(str(build)) >= _V3_4_BUILD_CUTOFF:
                LOGGER.debug("Detected V3_4 via lastBuildTime=%s", build)
                return ApiVariant.V3_4
        except ValueError:
            pass

    LOGGER.debug("Detected LEGACY variant (gitTag=%r)", tag)
    return ApiVariant.LEGACY
