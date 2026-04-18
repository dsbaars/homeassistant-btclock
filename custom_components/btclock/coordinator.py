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

    # ---- Settings patch + reload ------------------------------------------

    async def async_patch_settings(self, patch: dict) -> None:
        """Apply a partial settings update and reload cached settings.

        Entities that read from `client.settings` (Nostr switches, Nostr relay
        sensor, etc.) pick up the change on the next state read.
        """
        try:
            await self.client.async_patch_settings(patch)
            await self.client.async_load_settings()
        except BtclockAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        # In events mode, nothing polls — fetch status once so attribute-backed
        # entities (e.g. frontlight brightness) refresh immediately.
        if self._mode == UPDATE_MODE_EVENTS:
            try:
                data = await self.client.async_update_status()
                self.async_set_updated_data(data)
            except BtclockCommunicationError:
                pass
        else:
            await self.async_request_refresh()

    # ---- Poll-mode implementation -----------------------------------------

    async def _async_update_data(self) -> Status:
        """Only called in polling mode (update_interval is None otherwise)."""
        try:
            return await self.client.async_update_status()
        except BtclockAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except BtclockCommunicationError as err:
            raise UpdateFailed(str(err)) from err
