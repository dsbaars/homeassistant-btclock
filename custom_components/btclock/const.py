"""Constants for the BTClock integration."""

from __future__ import annotations

from logging import Logger, getLogger
from typing import Final

LOGGER: Logger = getLogger(__package__)

DOMAIN: Final = "btclock"
NAME: Final = "BTClock"
MANUFACTURER: Final = "BTClock"

# Config entry options
CONF_UPDATE_MODE: Final = "update_mode"
UPDATE_MODE_EVENTS: Final = "events"
UPDATE_MODE_POLLING: Final = "polling"
DEFAULT_UPDATE_MODE: Final = UPDATE_MODE_EVENTS
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 3600

# v4 caps every frontlight PWM write at 2048 (50 % of 12-bit): the seven
# channels share one 3V3 regulator. Higher values are rejected with 400.
# See btclock_v4 frontlight_logic/frontlight_duty.hpp `kMaxDuty`.
FRONTLIGHT_MAX_DUTY_V4: Final = 2048

SSE_RECONNECT_BACKOFF_MIN: Final = 2
SSE_RECONNECT_BACKOFF_MAX: Final = 60
REQUEST_TIMEOUT: Final = 10
