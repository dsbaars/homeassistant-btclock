"""Typed shapes for the BTClock HTTP API.

These mirror the 3.4.0 Swagger (https://git.btclock.dev/btclock/webui/raw/branch/feature/3.4.0/static/swagger.json)
but use `total=False` so they also accept legacy-firmware responses, which
omit some newer fields (httpAuthPassSet, ceEndpoint, hasFrontlight, …).
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import TypedDict


class ApiVariant(StrEnum):
    """Which BTClock firmware generation the client is talking to."""

    LEGACY = "legacy"
    V3_4 = "v3.4"


class DataSource(IntEnum):
    """Firmware-defined enum for settings.dataSource.

    The BTClock firmware (src/lib/system/config.cpp) routes upstream feeds
    differently per value — see `price_feed_connected` / `blocks_feed_connected`
    in the entity logic.
    """

    BTCLOCK = 0  # V2 relay (ws.btclock.dev)
    THIRD_PARTY = 1  # mempool.space + Kraken
    NOSTR = 2  # Nostr relay
    CUSTOM = 3  # custom V2-compatible endpoint


class LedDict(TypedDict, total=False):
    """One RGB LED in the status/lights response."""

    red: int
    green: int
    blue: int
    hex: str


class ConnectionStatus(TypedDict, total=False):
    """status.connectionStatus block."""

    price: bool
    blocks: bool
    V2: bool
    nostr: bool


class DndStatus(TypedDict, total=False):
    """status.dnd block."""

    enabled: bool
    dndTimeEnabled: bool
    startTime: str
    endTime: str
    active: bool


class Status(TypedDict, total=False):
    """Shape of GET /api/status and the SSE `status` event payload."""

    currentScreen: int
    numScreens: int
    timerRunning: bool
    isOTAUpdating: bool
    espUptime: int
    espFreeHeap: int
    espHeapSize: int
    connectionStatus: ConnectionStatus
    rssi: int
    currency: str
    data: list[str]
    leds: list[LedDict]
    dnd: DndStatus
    flStatus: list[int]
    lightLevel: int


class Screen(TypedDict, total=False):
    """One entry in settings.screens."""

    id: int
    name: str
    enabled: bool  # 3.4.0 only; legacy has no `enabled`


class Settings(TypedDict, total=False):
    """Subset of GET /api/settings that the integration reads.

    The live response has many more fields — we only type the ones we use.
    """

    hostname: str
    hostnamePrefix: str
    ip: str
    hwRev: str
    fsRev: str
    gitRev: str
    gitTag: str
    lastBuildTime: str
    numScreens: int
    screens: list[Screen]
    actCurrencies: list[str]
    availableCurrencies: list[str]
    hasFrontlight: bool
    hasLightLevel: bool
    httpAuthEnabled: bool
    httpAuthUser: str
    httpAuthPassSet: bool  # 3.4.0 only
    httpAuthPass: str  # legacy only
    otaPassSet: bool  # 3.4.0 only
    otaEnabled: bool
    dataSource: int
    nostrRelay: str
    nostrPubKey: str
    nostrZapPubkey: str
    nostrZapNotify: bool
    ledFlashOnZap: bool
    ledFlashOnUpd: bool
    stealFocus: bool


class SystemStatus(TypedDict, total=False):
    """Shape of GET /api/system_status."""

    espFreeHeap: int
    espHeapSize: int
    espFreePsram: int
    espPsramSize: int
    fsUsedBytes: int
    fsTotalBytes: int
    rssi: int
    txPower: int
