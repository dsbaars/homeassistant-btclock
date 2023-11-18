"""Light platform for btclock."""
from __future__ import annotations

from homeassistant.components.light import LightEntity, LightEntityDescription, ColorMode, ATTR_RGB_COLOR
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .coordinator import BtclockDataUpdateCoordinator
from .entity import BtclockEntity

ENTITY_DESCRIPTIONS = (
    LightEntityDescription(
        key="btclock_led",
        name="BTClock LEDs",
    ),
)


async def async_setup_entry(hass, entry, async_add_devices):
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]


    async_add_devices(
        BtclockLight(
            coordinator=coordinator,
            key=i
        )
        for i in range(len(coordinator.client._status_data.get('leds')))
    )


class BtclockLight(BtclockEntity, LightEntity):
    """btclock switch class."""

    def __init__(
        self,
        coordinator: BtclockDataUpdateCoordinator,
        key,
    ) -> None:
        """Initialize the switch class."""
        self._attr_supported_color_modes: set[ColorMode] = set()
        self._attr_supported_color_modes.add(ColorMode.RGB)
        self._attr_color_mode = ColorMode.RGB
        self.key = key
        super().__init__(coordinator)
        self.entity_description = LightEntityDescription(
            key=f"btclock_led_{(key+1)}",
            name=f"BTClock LED {(key+1)}",
        )

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self.coordinator.data.get("leds")[self.key].get("hex") != "#000000"

    @property
    def color_mode(self):
        """Return the color mode of the light."""
        return ColorMode.RGB

    async def async_turn_on(self, **kwargs: any) -> None:
        """Turn on the light."""
        rgb = kwargs.get(ATTR_RGB_COLOR)
        if (rgb):
            await self.coordinator.client.async_light_on(self.key, "{:02x}{:02x}{:02x}".format(*rgb))
            await self.coordinator.async_request_refresh()
        else:
            await self.coordinator.client.async_light_on(self.key, "FFFFFF")
            await self.coordinator.async_request_refresh()

    @property
    def unique_id(self):
        """Return the unique ID for this light."""
        return self.coordinator.config_entry.entry_id + "_led_" + str(self.key)

    @property
    def device_info(self):
        """Return the device info for this sensor."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name=self.coordinator.client._settings_data.get('hostname'),
            sw_version=self.coordinator.client._settings_data.get('gitRev'),
            model="V3"
        )

    async def async_turn_off(self, **_: any) -> None:
        """Turn off the light."""
        await self.coordinator.client.async_light_off(self.key)
        await self.coordinator.async_request_refresh()
