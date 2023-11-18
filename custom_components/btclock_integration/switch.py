"""Switch platform for integration_blueprint."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription

from .const import DOMAIN
from .coordinator import BtclockDataUpdateCoordinator
from .entity import BtclockEntity

ENTITY_DESCRIPTIONS = (
    SwitchEntityDescription(
        key="btclock_timer",
        name="BTClock Timer",
        icon="mdi:monitor-shimmer",
    ),
)


async def async_setup_entry(hass, entry, async_add_devices):
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_devices(
        BtclockSwitch(
            coordinator=coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
    )


class BtclockSwitch(BtclockEntity, SwitchEntity):
    """integration_blueprint switch class."""

    def __init__(
        self,
        coordinator: BtclockDataUpdateCoordinator,
        entity_description: SwitchEntityDescription,
    ) -> None:
        """Initialize the switch class."""
        super().__init__(coordinator)
        self.entity_description = entity_description

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self.coordinator.data.get("timerRunning")

    async def async_turn_on(self, **_: any) -> None:
        """Turn on the switch."""
        await self.coordinator.client.async_timer_start()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **_: any) -> None:
        """Turn off the switch."""
        await self.coordinator.client.async_timer_stop()
        await self.coordinator.async_request_refresh()
