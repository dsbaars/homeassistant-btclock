"""LED and frontlight entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BtclockConfigEntry
from .coordinator import BtclockCoordinator
from .entity import BtclockEntity
from .models import ApiVariant, LedDict

_OFF_HEX = "#000000"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BtclockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    leds: list[LedDict] = list(coordinator.data.get("leds") or [])

    entities: list[LightEntity] = [BtclockLed(coordinator, i) for i in range(len(leds))]
    if (
        coordinator.client.variant is ApiVariant.V3_4
        and coordinator.client.settings.get("hasFrontlight")
    ):
        entities.append(BtclockFrontlight(coordinator))

    async_add_entities(entities)


class BtclockLed(BtclockEntity, LightEntity):
    """One of the status LEDs under the display."""

    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_translation_key = "led"

    def __init__(self, coordinator: BtclockCoordinator, index: int) -> None:
        super().__init__(coordinator)
        self._index = index
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_led_{index}"
        self._attr_translation_placeholders = {"index": str(index + 1)}

    @property
    def _led(self) -> LedDict | None:
        leds = self.coordinator.data.get("leds") or []
        return leds[self._index] if self._index < len(leds) else None

    @property
    def is_on(self) -> bool:
        led = self._led
        return bool(led) and led.get("hex", _OFF_HEX).upper() != _OFF_HEX.upper()

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        led = self._led
        if not led:
            return None
        return (
            int(led.get("red", 0)),
            int(led.get("green", 0)),
            int(led.get("blue", 0)),
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        rgb = kwargs.get(ATTR_RGB_COLOR) or self.rgb_color or (255, 255, 255)
        if rgb == (0, 0, 0):
            rgb = (255, 255, 255)
        await self.coordinator.async_set_led(self._index, rgb)

    async def async_turn_off(self, **_: Any) -> None:
        await self.coordinator.async_set_led(self._index, (0, 0, 0))


class BtclockFrontlight(BtclockEntity, LightEntity):
    """The PWM frontlight on Rev B (3.4.0 only)."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_translation_key = "frontlight"

    def __init__(self, coordinator: BtclockCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_frontlight"
        self._max_raw = int(coordinator.client.settings.get("flMaxBrightness") or 65535)
        self._on_state = False
        self._brightness_ha = 255

    @callback
    def _handle_coordinator_update(self) -> None:
        # Infer on/off from flStatus (list of raw levels, one per display).
        fl_status = self.coordinator.data.get("flStatus") or []
        if fl_status:
            raw = max(fl_status)
            self._on_state = raw > 0
            self._brightness_ha = min(
                255, int(round(raw / max(self._max_raw, 1) * 255))
            )
        super()._handle_coordinator_update()

    @property
    def is_on(self) -> bool:
        return self._on_state

    @property
    def brightness(self) -> int | None:
        return self._brightness_ha if self._on_state else 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.client
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        raw = (
            int(round(brightness / 255 * self._max_raw))
            if brightness is not None
            else self._max_raw
        )
        if brightness is not None:
            await client.async_frontlight_brightness(raw)
        await client.async_frontlight_on()
        # Optimistic update — mirror raw values across all displays.
        fl_len = len(self.coordinator.data.get("flStatus") or [])
        self.coordinator.async_apply_optimistic({"flStatus": [raw] * max(fl_len, 1)})

    async def async_turn_off(self, **_: Any) -> None:
        await self.coordinator.client.async_frontlight_off()
        fl_len = len(self.coordinator.data.get("flStatus") or [])
        self.coordinator.async_apply_optimistic({"flStatus": [0] * max(fl_len, 1)})
