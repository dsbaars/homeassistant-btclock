"""Data coordinator for BTClock.

Two modes, chosen by the user in the config flow:

- **events**: subscribe to the device's `/events` SSE stream. Entities update
  on push; `update_interval` is `None` so the coordinator never polls. The
  SSE client auto-reconnects with jittered backoff on transient failures.

- **polling**: plain `/api/status` polling at the configured interval. No SSE.

Whichever mode is active, a settings PATCH is still followed by an explicit
refresh so settings-derived entities see the new value immediately.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BtclockAuthError, BtclockClient, BtclockCommunicationError
from .const import (
    CONF_UPDATE_MODE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UPDATE_MODE,
    DOMAIN,
    LOGGER,
    UPDATE_MODE_EVENTS,
    UPDATE_MODE_POLLING,
)
from .models import Status
from .sse import BtclockEventStream

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


class BtclockCoordinator(DataUpdateCoordinator[Status]):
    """Coordinated status updates for one BTClock device."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: BtclockClient,
    ) -> None:
        mode = config_entry.options.get(CONF_UPDATE_MODE, DEFAULT_UPDATE_MODE)
        scan_interval = int(
            config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        update_interval = (
            timedelta(seconds=scan_interval) if mode == UPDATE_MODE_POLLING else None
        )
        super().__init__(
            hass=hass,
            logger=LOGGER,
            name=f"{DOMAIN}:{client.host}",
            config_entry=config_entry,
            update_interval=update_interval,
        )
        self.client = client
        self._mode = mode
        self._stream: BtclockEventStream | None = None
        self._stream_task: asyncio.Task[None] | None = None
        # LED writes are array-based: every POST sends the full 4-element array.
        # Serialize with this lock so concurrent `async_set_led` calls chain
        # their mutations through the same in-memory state instead of racing
        # on stale views of `coordinator.data`.
        self._leds_lock = asyncio.Lock()

    @property
    def update_mode(self) -> str:
        return self._mode

    # ---- Lifecycle ---------------------------------------------------------

    async def async_start(self) -> None:
        """Kick off whichever update mechanism the user chose."""
        if self._mode == UPDATE_MODE_EVENTS:
            await self._start_push()
        # Polling mode needs no setup — DataUpdateCoordinator handles it.

    async def async_stop(self) -> None:
        await self._stop_push()

    # ---- SSE push ----------------------------------------------------------

    async def _start_push(self) -> None:
        if self._stream is not None:
            return
        self._stream = BtclockEventStream(
            self.client,
            on_status=self._on_status_frame,
        )
        self._stream_task = self.config_entry.async_create_background_task(
            self.hass, self._stream.run(), name=f"{self.name}-sse"
        )

    async def _stop_push(self) -> None:
        if self._stream is not None:
            await self._stream.stop()
        if self._stream_task is not None:
            self._stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._stream_task
        self._stream = None
        self._stream_task = None

    async def _on_status_frame(self, payload: Status) -> None:
        """SSE delivered a new status — publish it to entities."""
        self.async_set_updated_data(payload)

    # ---- Optimistic updates ------------------------------------------------

    def async_apply_optimistic(self, patch: dict) -> None:
        """Merge a partial status dict into coordinator.data and notify entities.

        Used by control entities (lights, switches, selects) to give immediate
        UI feedback after a successful write, without waiting for SSE or a
        poll to round-trip. The next authoritative update (SSE frame or scan)
        will supersede this view.
        """
        merged: Status = {**(self.data or {}), **patch}
        self.async_set_updated_data(merged)

    async def async_set_led(self, index: int, rgb: tuple[int, int, int]) -> None:
        """Atomically change one LED on the device + in coordinator.data.

        Held under `_leds_lock` so back-to-back calls (e.g. the user tapping
        four LED tiles in quick succession) serialize cleanly: each call
        sees the previous call's optimistic update and carries all the
        accumulated colors in its POST payload.
        """
        async with self._leds_lock:
            leds = list(self.data.get("leds") or [])
            if index >= len(leds):
                return
            hex_code = "#{:02X}{:02X}{:02X}".format(*rgb)
            payload = [{"hex": led.get("hex", "#000000")} for led in leds]
            payload[index] = {"hex": hex_code}
            await self.client.async_set_lights(payload)
            optimistic = [dict(led) for led in leds]
            optimistic[index] = {
                "hex": hex_code,
                "red": rgb[0],
                "green": rgb[1],
                "blue": rgb[2],
            }
            self.async_apply_optimistic({"leds": optimistic})

    # ---- Settings patch + reload ------------------------------------------

    async def async_patch_settings(self, patch: dict) -> None:
        """Apply a partial settings update optimistically and reload on success.

        The cached `client.settings` dict is mutated with `patch` *before* the
        HTTP call so dependent entities (Nostr switches, relay sensor, …)
        repaint instantly. After the PATCH returns, we reload settings from
        the device to reconcile with whatever the firmware actually accepted.
        On failure we revert to the last known server-side settings.
        """
        original = dict(self.client.settings or {})
        # Optimistically mutate the cached settings + notify listeners.
        self.client._settings = {**original, **patch}  # noqa: SLF001
        self.async_update_listeners()

        try:
            await self.client.async_patch_settings(patch)
        except BtclockAuthError as err:
            self.client._settings = original  # noqa: SLF001
            self.async_update_listeners()
            raise ConfigEntryAuthFailed(str(err)) from err
        except BtclockCommunicationError:
            self.client._settings = original  # noqa: SLF001
            self.async_update_listeners()
            raise

        # Reconcile — pull authoritative settings back from the device.
        # Keep the optimistic state if the reload fails; next successful
        # load will resync.
        with contextlib.suppress(BtclockCommunicationError):
            await self.client.async_load_settings()
        self.async_update_listeners()

    # ---- Poll-mode implementation -----------------------------------------

    async def _async_update_data(self) -> Status:
        """Only called in polling mode (update_interval is None otherwise)."""
        try:
            return await self.client.async_update_status()
        except BtclockAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except BtclockCommunicationError as err:
            raise UpdateFailed(str(err)) from err
