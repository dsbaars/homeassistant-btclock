# Brand assets

Icon and wordmark for the BTClock Home Assistant integration, set in Ubuntu Medium Italic.

| Asset | Size | Description |
|---|---|---|
| `icon.svg`   | 256×256   | Source — "BTClock" in Bitcoin orange (`#F7931A`) on a near-black rounded tile (`#111111`) |
| `icon.png`   | 256×256   | Raster 1× |
| `icon@2x.png` | 512×512  | Raster 2× |
| `logo.svg`   | 600×200   | Source wordmark — "BTClock" in near-black (`#111111`) on transparent |
| `logo.png`   | 600×200   | Raster 1× |
| `logo@2x.png` | 1200×400 | Raster 2× |
| `dark_logo.svg`   | 600×200   | Source — same wordmark in Bitcoin orange for dark themes |
| `dark_logo.png`   | 600×200   | Raster 1× |
| `dark_logo@2x.png` | 1200×400 | Raster 2× |
| `dark_icon.png`   | 256×256   | Same design as `icon.png` — the near-black tile already reads well on dark themes, but shipping an explicit copy avoids relying on the brands proxy's fallback chain |
| `dark_icon@2x.png` | 512×512  | Raster 2× |

## Use in Home Assistant

Home Assistant 2026.3+ reads this `brand/` folder directly ([announcement](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api)); no other setup is required. The `home-assistant/brands` repository [stopped accepting custom-integration PRs](https://github.com/home-assistant/brands/pull/10167) at the same time, so HA < 2026.3 will fall back to the generic integration icon for BTClock.

## Regenerating from source

Ubuntu Medium Italic is loaded via `font-family="Ubuntu"` + `font-weight="500"` + `font-style="italic"`. To rerender from the SVGs:

```
rsvg-convert -w 256  -h 256  icon.svg -o icon.png
rsvg-convert -w 512  -h 512  icon.svg -o icon@2x.png
rsvg-convert -w 600  -h 200  logo.svg -o logo.png
rsvg-convert -w 1200 -h 400  logo.svg -o logo@2x.png
rsvg-convert -w 600  -h 200  dark_logo.svg -o dark_logo.png
rsvg-convert -w 1200 -h 400  dark_logo.svg -o dark_logo@2x.png
```

The system must have Ubuntu Medium Italic (500 italic) installed. Download from Google Fonts if absent.
