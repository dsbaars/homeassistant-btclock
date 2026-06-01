"""Typed shapes for the BTClock HTTP API.

These mirror the published OpenAPI specs — v3
(https://git.btclock.dev/btclock/webui/src/branch/v3/static/openapi.yml) and v4
(https://git.btclock.dev/btclock/webui/src/branch/v4/static/openapi.yml) — but
use `total=False` so a single TypedDict accepts every firmware generation:
legacy responses omit newer fields (httpAuthPassSet, ceEndpoint, hasFrontlight,
…), while v4 renames/reshapes a few (priceSymMode, nostrRelays, the
`availableFonts` object list, and the nested `frontlight` status block).
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import TypedDict


class ApiVariant(StrEnum):
    """Which BTClock firmware generation the client is talking to."""

    LEGACY = "legacy"
    V3_4 = "v3.4"
    V4 = "v4"


# v3.4 (Arduino) and v4 (ESP-IDF) share the same POST-style endpoint set
# and JSON shapes — `MODERN_VARIANTS` is the gate for entities/services
# that work on either, distinct from `LEGACY` (GET-based, ≤3.3.x).
MODERN_VARIANTS: frozenset[ApiVariant] = frozenset({ApiVariant.V3_4, ApiVariant.V4})


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


class NostrRelayStatus(TypedDict, total=False):
    """One relay's live state in connectionStatus.nostr (v4 ≥ rc.4)."""

    url: str
    connected: bool


class ConnectionStatus(TypedDict, total=False):
    """status.connectionStatus block."""

    price: bool
    blocks: bool
    V2: bool
    # Pre-rc.4 firmware emitted `nostr` as a single bool; v4 ≥ rc.4 emits a
    # per-relay array. Use `nostr_connected()` to read it shape-agnostically.
    nostr: bool | list[NostrRelayStatus]
    nwc: bool  # v4: live NIP-47 Nostr Wallet Connect state


def nostr_connected(cs: ConnectionStatus | None) -> bool | None:
    """Collapse connectionStatus.nostr to a single connected flag.

    v4 (≥ rc.4) reports `nostr` as a per-relay array of `{url, connected}`;
    older firmware reports a single bool. Returns True if any relay is up,
    the bool as-is on legacy shape, or None when the field is absent.
    """
    nostr = (cs or {}).get("nostr")
    if isinstance(nostr, list):
        return any(relay.get("connected") for relay in nostr)
    return nostr


class DndStatus(TypedDict, total=False):
    """status.dnd block."""

    enabled: bool
    dndTimeEnabled: bool
    startTime: str
    endTime: str
    active: bool


class Frontlight(TypedDict, total=False):
    """status.frontlight block (v4 only).

    v4 firmware nests live frontlight state here instead of the flat
    `flStatus` array v3.x emits. `coordinator._normalize_frontlight` maps
    `duties` back onto `flStatus` so the light entity has one shape to read.
    """

    on: bool
    duties: list[int]  # per-panel 12-bit duty (0..4095)
    targetDuty: int
    configuredBrightness: int


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
    flStatus: list[int]  # v3.x; v4 nests this under `frontlight.duties`
    frontlight: Frontlight  # v4 only
    lightLevel: int


class Screen(TypedDict, total=False):
    """One entry in settings.screens."""

    id: int
    name: str
    enabled: bool  # 3.4.0 only; legacy has no `enabled`
    order: int  # 3.4.1+ rotation order; older firmware omits it


class AvailableFont(TypedDict, total=False):
    """One entry in settings.availableFonts on v4 firmware.

    v3 firmware lists fonts as plain id strings; v4 wraps each in an object
    so the WebUI can disable the ₿ price-marker when the active font lacks
    the glyph. `select._font_options` accepts either shape.
    """

    id: str
    hasBtcSymbol: bool


class DndSettings(TypedDict, total=False):
    """settings.dnd block (3.4.0+).

    Distinct from DndStatus: this one holds the schedule configuration,
    not the runtime flags.
    """

    enabled: bool
    dndTimeEnabled: bool
    startHour: int
    startMinute: int
    endHour: int
    endMinute: int


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
    nostrRelay: str  # deprecated in v4 in favour of nostrRelays
    nostrRelays: list[str]  # v4: up to 4 relay URLs
    nostrPubKey: str
    nostrZapPubkey: str  # deprecated in v4 in favour of nostrZapPubkeys
    nostrZapPubkeys: list[str]  # v4: up to 8 pubkeys
    nostrZapNotify: bool
    ledFlashOnZap: bool
    ledFlashOnUpd: bool
    ledBrightness: int
    disableLeds: bool
    stealFocus: bool
    useSatsSymbol: bool  # v3 only; v4 replaces it with priceSymMode
    priceSymMode: int  # v4: 0 none, 1 Satoshi symbol, 2 bitcoin sign ₿
    decimalShareDot: bool  # v4 rename of v3 suffixShareDot
    fontName: str
    availableFonts: list[str] | list[AvailableFont]  # v3: strings; v4: objects
    availablePools: list[str]
    wifiMac: str  # v4: device WiFi MAC (readonly)
    # Nostr Wallet Connect (NIP-47), v4 only.
    nwcEnabled: bool  # master toggle (boot-only)
    nwcRefreshSecs: int  # balance poll cadence, 15..3600 (boot-only)
    nwcShowNotify: bool  # show the on-screen payment overlay (live)
    nwcFlashOnPay: bool  # LED/frontlight pulse on payment (live)
    nwcUriSet: bool  # readonly: a pairing URI is stored
    nwcUriMasked: str  # readonly: redacted fingerprint of the pairing URI
    gitReleaseUrl: str
    tzString: str
    dnd: DndSettings


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
