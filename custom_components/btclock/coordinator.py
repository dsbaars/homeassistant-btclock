"""Data coordinator for BTClock — SSE push with polling fallback.

The coordinator attaches to the device's `/events` SSE stream and forwards
`status` frames to entities via `async_set_updated_data`. If the SSE stream
fails repeatedly (e.g. legacy firmware that misbehaves, network flake), it
falls back to `/api/status` polling at `DEFAULT_SCAN_INTERVAL`. A slow poll
heartbeat runs alongside SSE anyway so stale data is caught.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BtclockAuthError, BtclockClient, BtclockCommunicationError
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    SSE_FAILURE_THRESHOLD,
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
        super().__init__(
            hass=hass,
            logger=LOGGER,
            name=f"{DOMAIN}:{client.host}",
            config_entry=config_entry,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self._stream: BtclockEventStream | None = None
        self._stream_task: asyncio.Task[None] | None = None

    # ---- Push setup --------------------------------------------------------

    async def async_start_push(self) -> None:
        """Open the SSE stream. Safe to call once per config-entry setup."""
        if self._stream is not None:
            return
        self._stream = BtclockEventStream(
            self.client,
            on_status=self._on_status_frame,
            on_disconnect=self._on_sse_disconnect,
        )
        self._stream_task = self.config_entry.async_create_background_task(
            self.hass, self._stream.run(), name=f"{self.name}-sse"
        )

    async def async_stop_push(self) -> None:
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

    async def _on_sse_disconnect(self, err: BaseException | None) -> None:
        if (
            self._stream is not None
            and self._stream.consecutive_failures >= SSE_FAILURE_THRESHOLD
        ):
            LOGGER.info(
                "SSE stream to %s has failed %d times; relying on polling heartbeat",
                self.client.host,
                self._stream.consecutive_failures,
            )

    # ---- Poll heartbeat ----------------------------------------------------

    async def _async_update_data(self) -> Status:
        """Poll fallback — also acts as a heartbeat alongside SSE."""
        try:
            return await self.client.async_update_status()
        except BtclockAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except BtclockCommunicationError as err:
            raise UpdateFailed(str(err)) from err
