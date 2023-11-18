# BTClock Integration

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

_Integration to integrate with [BTClock][https://github.com/btclock]._

**This integration will set up the following platforms.**

Platform | Description
-- | --
`binary_sensor` | Show data soure connection status
`light` | Control the LEDs
`select` | Control the screen shown
`sensor` | View the current screen shown
`switch` | Control the screen timer

## Installation

1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
1. If you do not have a `custom_components` directory (folder) there, you need to create it.
1. In the `custom_components` directory (folder) create a new folder called `btclock`.
1. Download _all_ the files from the `custom_components/btclock/` directory (folder) in this repository.
1. Place the files you downloaded in the new directory (folder) you created.
1. Restart Home Assistant
1. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "BTClock"

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)