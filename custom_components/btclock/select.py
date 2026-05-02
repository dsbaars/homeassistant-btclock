"""Select entities: screen + currency."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BtclockConfigEntry
from .coordinator import BtclockCoordinator
from .entity import BtclockEntity
from .models import MODERN_VARIANTS, ApiVariant


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BtclockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = [BtclockScreenSelect(coordinator)]
    if (
        coordinator.client.variant in MODERN_VARIANTS
        and coordinator.client.settings.get("actCurrencies")
    ):
        entities.append(BtclockCurrencySelect(coordinator))
    # v4 ships real catalogues for `availablePools` / `availableFonts`;
    # v3.4 emits a placeholder `[""]` so we filter to "more than the empty
    # placeholder" rather than gating strictly on variant.
    if coordinator.client.variant is ApiVariant.V4:
        if _has_real_catalog(coordinator.client.settings.get("availablePools")):
            entities.append(BtclockMiningPoolSelect(coordinator))
        if _has_real_catalog(coordinator.client.settings.get("availableFonts")):
            entities.append(BtclockFontSelect(coordinator))
    async_add_entities(entities)


def _has_real_catalog(catalog: list[str] | None) -> bool:
    """Return True when the catalogue lists at least one non-empty option."""
    return bool(catalog) and any(item for item in catalog if item)


class BtclockScreenSelect(BtclockEntity, SelectEntity):
    _attr_translation_key = "screen"
    _attr_icon = "mdi:monitor"

    def __init__(self, coordinator: BtclockCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_screen"

    def _screens(self) -> list[dict]:
        """All screens, enabled or not, in the device's rotation order.

        The firmware lets a client switch to any screen via
        POST /api/show/screen regardless of its `enabled` flag — that only
        controls whether the screen appears in auto-rotation
        (src/lib/ui/screen_handler.cpp:148). So we expose the full list.

        Firmware ≥3.4 emits an explicit `order` int per screen for the
        user-configured rotation order; when present we sort by it so the
        dropdown matches what the device actually rotates through. Older
        firmware omits the field — fall back to array order.
        """
        screens = list(self.coordinator.client.settings.get("screens") or [])
        if screens and all("order" in s for s in screens):
            screens.sort(key=lambda s: s["order"])
        return screens

    @property
    def options(self) -> list[str]:
        return [s.get("name", "") for s in self._screens()]

    @property
    def current_option(self) -> str | None:
        current_id = self.coordinator.data.get("currentScreen")
        for s in self._screens():
            if s.get("id") == current_id:
                return s.get("name")
        return None

    async def async_select_option(self, option: str) -> None:
        for s in self._screens():
            if s.get("name") == option:
                screen_id = int(s["id"])
                await self.coordinator.client.async_set_screen(screen_id)
                self.coordinator.async_apply_optimistic({"currentScreen": screen_id})
                return


class BtclockCurrencySelect(BtclockEntity, SelectEntity):
    _attr_translation_key = "currency"
    _attr_icon = "mdi:currency-usd"

    def __init__(self, coordinator: BtclockCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_currency"

    @property
    def options(self) -> list[str]:
        return list(self.coordinator.client.settings.get("actCurrencies") or [])

    @property
    def current_option(self) -> str | None:
        return self.coordinator.data.get("currency")

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.client.async_set_currency(option)
        self.coordinator.async_apply_optimistic({"currency": option})


class BtclockMiningPoolSelect(BtclockEntity, SelectEntity):
    """Pick the upstream mining-pool data source (v4 only).

    v4 firmware fetches hashrate / earnings stats from one of the pools
    listed in `availablePools`. Some pools (`viabtc`, `foundry_usa`) treat
    `miningPoolUser` as a secret API key — those are still selectable but
    the user must set the key separately on the device.
    """

    _attr_translation_key = "mining_pool"
    _attr_icon = "mdi:pickaxe"

    def __init__(self, coordinator: BtclockCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_mining_pool"

    @property
    def options(self) -> list[str]:
        return [
            p
            for p in (self.coordinator.client.settings.get("availablePools") or [])
            if p
        ]

    @property
    def current_option(self) -> str | None:
        return self.coordinator.client.settings.get("miningPoolName") or None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_patch_settings({"miningPoolName": option})


class BtclockFontSelect(BtclockEntity, SelectEntity):
    """Pick the on-device EPD font (v4 only)."""

    _attr_translation_key = "font"
    _attr_icon = "mdi:format-font"

    def __init__(self, coordinator: BtclockCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_font"

    @property
    def options(self) -> list[str]:
        return [
            f
            for f in (self.coordinator.client.settings.get("availableFonts") or [])
            if f
        ]

    @property
    def current_option(self) -> str | None:
        return self.coordinator.client.settings.get("fontName") or None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_patch_settings({"fontName": option})
