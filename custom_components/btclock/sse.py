"""Tiny Server-Sent-Events client for the BTClock `/events` stream.

BTClock emits two event types:
  - `welcome` — sent once on connect, payload is a millis() uptime value.
  - `status`  — periodic (~5 s) JSON matching GET /api/status.

The SSE frame format we need to handle:

    event: status
    data: {"currentScreen":0,...}

    (blank line terminates a frame)

We ignore id: and retry: fields — BTClock doesn't emit them.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import aiohttp

from .api import BtclockAuthError, BtclockClient
from .const import (
    LOGGER,
    SSE_RECONNECT_BACKOFF_MAX,
    SSE_RECONNECT_BACKOFF_MIN,
)


async def _iter_events(resp: aiohttp.ClientResponse) -> AsyncIterator[tuple[str, str]]:
    """Yield (event_name, raw_data) pairs from an SSE response body."""
    event = "message"
    data_lines: list[str] = []

    async for raw in resp.content:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")

        if line == "":
            # Frame terminator
            if data_lines:
                yield event, "\n".join(data_lines)
            event = "message"
            data_lines = []
            continue

        if line.startswith(":"):
            # Comment — used as keep-alive by some servers; ignore.
            continue

        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]

        if field == "event":
            event = value or "message"
        elif field == "data":
            data_lines.append(value)
        # id/retry intentionally ignored


class BtclockEventStream:
    """Maintain a reconnecting SSE connection to `/events`.

    Usage:

        stream = BtclockEventStream(client, on_status=lambda s: ...)
        task = asyncio.create_task(stream.run())
        ...
        await stream.stop()
        await task
    """

    def __init__(
        self,
        client: BtclockClient,
        *,
        on_status: Callable[[dict[str, Any]], Awaitable[None] | None],
        on_disconnect: Callable[[BaseException | None], Awaitable[None] | None]
        | None = None,
    ) -> None:
        self._client = client
        self._on_status = on_status
        self._on_disconnect = on_disconnect
        self._stopped = asyncio.Event()
        self._consecutive_failures = 0

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    async def stop(self) -> None:
        self._stopped.set()

    async def run(self) -> None:
        """Run until `stop()` is called. Reconnects with jittered backoff."""
        while not self._stopped.is_set():
            try:
                await self._connect_once()
                self._consecutive_failures = 0
            except BtclockAuthError:
                # Auth failure is not transient — surface immediately.
                raise
            except (TimeoutError, aiohttp.ClientError) as err:
                self._consecutive_failures += 1
                LOGGER.debug("SSE connection dropped (%s); will retry", err)
                if self._on_disconnect is not None:
                    result = self._on_disconnect(err)
                    if asyncio.iscoroutine(result):
                        await result

            if self._stopped.is_set():
                break

            # Exponential backoff with jitter, capped.
            delay = min(
                SSE_RECONNECT_BACKOFF_MAX,
                SSE_RECONNECT_BACKOFF_MIN * (2 ** min(self._consecutive_failures, 5)),
            )
            delay *= 0.5 + random.random() * 0.5
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=delay)

    async def _connect_once(self) -> None:
        url = self._client.url_for("events")
        LOGGER.debug("Opening SSE stream at %s", url)
        async with self._client.session.request(
            "GET",
            url,
            auth=self._client.auth,
            headers={"Accept": "text/event-stream"},
            timeout=aiohttp.ClientTimeout(total=None, sock_read=None),
        ) as resp:
            if resp.status in (401, 403):
                raise BtclockAuthError(f"Authentication required for {url}")
            resp.raise_for_status()

            async for event, raw in _iter_events(resp):
                if self._stopped.is_set():
                    return
                if event != "status":
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    LOGGER.debug("Skipping malformed SSE frame: %r", raw[:120])
                    continue
                result = self._on_status(payload)
                if asyncio.iscoroutine(result):
                    await result
