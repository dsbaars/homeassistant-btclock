"""Constants for the BTClock integration."""

from __future__ import annotations

from logging import Logger, getLogger
from typing import Final

LOGGER: Logger = getLogger(__package__)

DOMAIN: Final = "btclock"
NAME: Final = "BTClock"
MANUFACTURER: Final = "BTClock"

DEFAULT_SCAN_INTERVAL: Final = 30
SSE_RECONNECT_BACKOFF_MIN: Final = 2
SSE_RECONNECT_BACKOFF_MAX: Final = 60
SSE_FAILURE_THRESHOLD: Final = (
    3  # switch to poll-only after this many back-to-back failures
)
REQUEST_TIMEOUT: Final = 10
