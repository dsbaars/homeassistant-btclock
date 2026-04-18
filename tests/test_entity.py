"""Entity base tests — currently just the hwRev prettifier."""

from __future__ import annotations

import pytest

from custom_components.btclock.entity import _pretty_hw_rev


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("REV_B_EPD_2_13", 'Rev B (EPD 2.13")'),
        ("REV_A_EPD_2_13", 'Rev A (EPD 2.13")'),
        ("REV_B", "Rev B"),
        ("REV_C_EPD_2_9", 'Rev C (EPD 2.9")'),
        ("weird_value", "weird_value"),
        (None, "BTClock"),
        ("", "BTClock"),
    ],
)
def test_pretty_hw_rev(raw: str | None, expected: str) -> None:
    assert _pretty_hw_rev(raw) == expected
