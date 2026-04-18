# Brand assets

Icon and wordmark for the BTClock Home Assistant integration, set in Ubuntu Medium Italic with Bitcoin orange (`#F7931A`).

| Asset | Size | Purpose |
|---|---|---|
| `icon.svg`   | 256×256 | Source — "BT" monogram on orange rounded tile |
| `icon.png`   | 256×256 | Raster 1× |
| `icon@2x.png` | 512×512 | Raster 2× |
| `logo.svg`   | 600×200 | Source wordmark — "BT" orange, "Clock" dark |
| `logo.png`   | 600×200 | Raster 1× |
| `logo@2x.png` | 1200×400 | Raster 2× |

## Use in Home Assistant

Home Assistant pulls integration branding from [home-assistant/brands](https://github.com/home-assistant/brands), **not** from this repo. To show these icons in the HA UI, submit a PR against that repo that creates `custom_integrations/btclock/` containing `icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`.

## Regenerating from source

Ubuntu Medium Italic is loaded via `font-family="Ubuntu"` + `font-weight="500"` + `font-style="italic"`. To rerender from the SVGs:

```
rsvg-convert -w 256  -h 256  icon.svg -o icon.png
rsvg-convert -w 512  -h 512  icon.svg -o icon@2x.png
rsvg-convert -w 600  -h 200  logo.svg -o logo.png
rsvg-convert -w 1200 -h 400  logo.svg -o logo@2x.png
```

The system must have Ubuntu Medium Italic (500 italic) installed. Download from Google Fonts if absent.
