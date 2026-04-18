"""Shared base class for BTClock entities."""

from __future__ import annotations

import re

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import BtclockCoordinator

# Firmware reports hwRev like "REV_B_EPD_2_13" → "Rev B (EPD 2.13\")".
# Fall back to the raw string when the shape is unexpected.
_HW_REV_RE = re.compile(r"^REV_([A-Z])(?:_EPD_(\d+)_(\d+))?$")


def _pretty_hw_rev(raw: str | None) -> str:
    if not raw:
        return "BTClock"
    m = _HW_REV_RE.match(raw)
    if not m:
        return raw
    letter, major, minor = m.groups()
    if major and minor:
        return f'Rev {letter} (EPD {major}.{minor}")'
    return f"Rev {letter}"


class BtclockEntity(CoordinatorEntity[BtclockCoordinator]):
    """Base entity: binds to the per-device DataUpdateCoordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BtclockCoordinator) -> None:
        super().__init__(coordinator)
        settings = coordinator.client.settings
        hostname = settings.get("hostname") or coordinator.client.host
        sw_version = settings.get("gitTag") or settings.get("gitRev")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name=hostname,
            manufacturer=MANUFACTURER,
            model=_pretty_hw_rev(settings.get("hwRev")),
            sw_version=sw_version,
            configuration_url=f"http://{coordinator.client.host}/",
        )
