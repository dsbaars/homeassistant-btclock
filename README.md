# BTClock Integration

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

_Home Assistant integration for the [BTClock](https://git.btclock.dev/btclock/btclock_v3) — an open-source Bitcoin price / block-height display._

## Supported firmware

| Firmware               | Status    | Notes                                                 |
|------------------------|-----------|-------------------------------------------------------|
| 3.4.0+                 | Full      | POST-style API, SSE push updates, HTTP auth, DND, frontlight |
| 3.3.x and earlier      | Basic     | GET-style API; read-only DND and no frontlight controls |

The variant is detected automatically from `GET /api/settings`.

## Platforms

| Platform        | Entities                                                                  |
|-----------------|---------------------------------------------------------------------------|
| `sensor`        | Current screen, currency, uptime, RSSI, free heap, ambient light level    |
| `binary_sensor` | Price / blocks / V2 / nostr feed connectivity, screen timer, OTA, DND     |
| `switch`        | Screen timer, Do-not-disturb (3.4.0+)                                     |
| `select`        | Screen, currency (3.4.0+)                                                 |
| `light`         | One entity per status LED, plus frontlight (when hardware present)        |
| `button`        | Identify, restart, full refresh, next / previous screen, flash frontlight (3.4.0+) |

## Data-source sensors

`connectionStatus` exposes four separate feeds — `price`, `blocks`, `V2`, `nostr` — because a BTClock can be driven by any combination of them depending on its `dataSource` setting. The integration exposes a binary sensor per feed:

- **Price / Blocks feed** — always enabled by default (the common case — BTClock driven by the built-in mempool source).
- **V2 / Nostr feed** — hidden by default, but **auto-enabled at integration setup if the feed is already connected**. If you later switch the device's `dataSource`, toggle the sensor visibility manually in Home Assistant's entity registry or reconfigure the integration.

## Live updates

When the firmware exposes `/events`, the integration subscribes to the SSE stream and updates entities on push. If the stream drops, it falls back to polling `/api/status` until SSE recovers.

## HTTP Basic Auth

If the BTClock has `httpAuthEnabled` turned on, the config flow will prompt for credentials. When credentials stop working (e.g. you rotated the password on the device), Home Assistant will surface a reauth prompt.

## Installation via HACS

1. Open HACS → Integrations → menu → **Custom repositories**.
2. Add `https://git.btclock.dev/btclock/homeassistant-btclock` with category **Integration**.
3. Install "BTClock Integration" and restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → BTClock**, or accept the auto-discovered zeroconf prompt.

## Manual installation

1. Copy `custom_components/btclock/` into your Home Assistant configuration's `custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration from **Settings → Devices & Services**.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). Recommended workflow is to use the VSCode Dev Container (`.devcontainer.json` ships Python 3.13 + HA latest + test deps). Useful scripts:

- `scripts/setup`  – install runtime + test deps
- `scripts/test`   – run `pytest tests/`
- `scripts/check`  – ruff lint + format check + pytest
- `scripts/develop` – boot a debug Home Assistant on port 8123 with this integration loaded (set `BTCLOCK_DEBUGPY=1` to attach on port 5678)

## Contributing

Issues and pull requests welcome at <https://git.btclock.dev/btclock/homeassistant-btclock> or the GitHub mirror.
