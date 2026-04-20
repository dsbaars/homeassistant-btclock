"""Optimistic-update regression tests.

These lock in the behaviour from v0.4.1: any control (light, switch,
select) must apply its new state to `coordinator.data` immediately after
a successful write, so the UI doesn't hang on an SSE/poll round-trip.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.btclock.api import BtclockClient
from custom_components.btclock.const import DOMAIN
from custom_components.btclock.models import ApiVariant


async def _setup(hass: HomeAssistant, settings: dict, status: dict) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=settings["hostname"],
        data={CONF_HOST: settings["hostname"] + ".local"},
    )
    entry.add_to_hass(hass)

    async def _fake_load(self: BtclockClient) -> dict:
        self._settings = settings  # noqa: SLF001
        self._variant = ApiVariant.V3_4  # noqa: SLF001
        return settings

    with (
        patch.object(BtclockClient, "async_load_settings", _fake_load),
        patch.object(
            BtclockClient, "async_update_status", new=AsyncMock(return_value=status)
        ),
        patch(
            "custom_components.btclock.coordinator.BtclockCoordinator.async_start",
            new=AsyncMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


@pytest.fixture
def status_leds_off(load_fixture) -> dict:
    status = load_fixture("status_v3_4_revb").copy()
    status["leds"] = [
        {"hex": "#000000", "red": 0, "green": 0, "blue": 0},
        {"hex": "#000000", "red": 0, "green": 0, "blue": 0},
        {"hex": "#000000", "red": 0, "green": 0, "blue": 0},
        {"hex": "#000000", "red": 0, "green": 0, "blue": 0},
    ]
    return status


async def test_led_turn_on_updates_state_without_refresh(
    hass: HomeAssistant, load_fixture, status_leds_off
) -> None:
    """Flipping an LED on should mark it on in coordinator.data *before* any
    refresh happens — proves the optimistic path."""
    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status_leds_off)
    coord = entry.runtime_data

    refreshed = False

    async def _boom(*_a, **_kw):
        nonlocal refreshed
        refreshed = True

    with (
        patch.object(BtclockClient, "async_set_lights", new=AsyncMock()),
        patch.object(coord, "async_request_refresh", side_effect=_boom),
    ):
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": "light.btclock_9d5530_led_1", "rgb_color": [255, 204, 0]},
            blocking=True,
        )

    assert refreshed is False, "optimistic path must not request a refresh"
    state = hass.states.get("light.btclock_9d5530_led_1")
    assert state.state == "on"
    assert state.attributes.get("rgb_color") == (255, 204, 0)
    # coordinator.data's leds[0] should reflect the new value
    assert coord.data["leds"][0]["hex"] == "#FFCC00"
    assert coord.data["leds"][0]["red"] == 255


async def test_led_turn_off_updates_state_without_refresh(
    hass: HomeAssistant, load_fixture
) -> None:
    status = load_fixture("status_v3_4_revb")
    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status)
    coord = entry.runtime_data

    with (
        patch.object(BtclockClient, "async_set_lights", new=AsyncMock()),
        patch.object(coord, "async_request_refresh") as refresh_mock,
    ):
        await hass.services.async_call(
            "light",
            "turn_off",
            {"entity_id": "light.btclock_9d5530_led_1"},
            blocking=True,
        )

    refresh_mock.assert_not_called()
    assert coord.data["leds"][0]["hex"] == "#000000"


async def test_timer_switch_optimistic(hass: HomeAssistant, load_fixture) -> None:
    status = load_fixture("status_v3_4_revb").copy()
    status["timerRunning"] = False
    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status)
    coord = entry.runtime_data

    with (
        patch.object(BtclockClient, "async_timer_start", new=AsyncMock()),
        patch.object(coord, "async_request_refresh") as refresh_mock,
    ):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.btclock_9d5530_screen_timer"},
            blocking=True,
        )

    refresh_mock.assert_not_called()
    assert coord.data["timerRunning"] is True


async def test_dnd_switch_reflects_active_state(
    hass: HomeAssistant, load_fixture
) -> None:
    """Scheduled DND pushes status.dnd.active=true with enabled=false; the
    switch must still show on, matching what the device is actually doing."""
    settings = load_fixture("settings_v3_4_revb").copy()
    settings["dnd"] = {
        **settings["dnd"],
        "dndTimeEnabled": True,
        "startHour": 23,
        "startMinute": 0,
        "endHour": 7,
        "endMinute": 0,
    }
    status = load_fixture("status_v3_4_dnd_active")
    await _setup(hass, settings, status)

    state = hass.states.get("switch.btclock_9d5530_do_not_disturb")
    assert state is not None
    assert state.state == "on"


async def test_dnd_switch_turn_off_blocked_by_schedule(
    hass: HomeAssistant, load_fixture
) -> None:
    """Inside the scheduled quiet window, turn_off would be a device no-op;
    raise HomeAssistantError instead and don't touch the API."""
    from datetime import datetime, time
    from unittest.mock import MagicMock

    from homeassistant.exceptions import HomeAssistantError

    settings = load_fixture("settings_v3_4_revb").copy()
    settings["tzString"] = "UTC0"
    settings["dnd"] = {
        **settings["dnd"],
        "dndTimeEnabled": True,
        "startHour": 23,
        "startMinute": 0,
        "endHour": 7,
        "endMinute": 0,
    }
    status = load_fixture("status_v3_4_dnd_active")
    entry = await _setup(hass, settings, status)
    coord = entry.runtime_data

    disable_mock = AsyncMock()
    frozen_now = datetime(2026, 4, 20, 3, 30)  # inside 23:00 → 07:00 window
    fake_dt = MagicMock(wraps=datetime)
    fake_dt.now = MagicMock(return_value=frozen_now)

    with (
        patch.object(BtclockClient, "async_dnd_disable", disable_mock),
        patch("custom_components.btclock.switch.datetime", fake_dt),
        patch("custom_components.btclock.switch.time", time),
        pytest.raises(HomeAssistantError, match="scheduled quiet hours"),
    ):
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": "switch.btclock_9d5530_do_not_disturb"},
            blocking=True,
        )

    disable_mock.assert_not_awaited()
    assert coord.data["dnd"]["active"] is True


async def test_dnd_switch_turn_off_outside_schedule(
    hass: HomeAssistant, load_fixture
) -> None:
    """Outside the quiet window, turn_off hits the API and clears optimistic
    active/enabled flags."""
    from datetime import datetime, time
    from unittest.mock import MagicMock

    settings = load_fixture("settings_v3_4_revb").copy()
    settings["tzString"] = "UTC0"
    settings["dnd"] = {
        **settings["dnd"],
        "dndTimeEnabled": True,
        "startHour": 23,
        "startMinute": 0,
        "endHour": 7,
        "endMinute": 0,
    }
    status = load_fixture("status_v3_4_dnd_active").copy()
    status["dnd"] = {**status["dnd"], "enabled": True, "active": True}
    entry = await _setup(hass, settings, status)
    coord = entry.runtime_data

    disable_mock = AsyncMock()
    frozen_now = datetime(2026, 4, 20, 12, 0)  # outside 23:00 → 07:00 window
    fake_dt = MagicMock(wraps=datetime)
    fake_dt.now = MagicMock(return_value=frozen_now)

    with (
        patch.object(BtclockClient, "async_dnd_disable", disable_mock),
        patch("custom_components.btclock.switch.datetime", fake_dt),
        patch("custom_components.btclock.switch.time", time),
    ):
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": "switch.btclock_9d5530_do_not_disturb"},
            blocking=True,
        )

    disable_mock.assert_awaited_once()
    assert coord.data["dnd"]["enabled"] is False
    assert coord.data["dnd"]["active"] is False


async def test_staggered_led_toggles_accumulate(
    hass: HomeAssistant, load_fixture, status_leds_off
) -> None:
    """Rapidly flipping LEDs 1→2→3→4 must end with all four set — no clobbering.

    The BTClock LED API overwrites the full 4-element array on every POST, so
    concurrent `_write_color` calls race unless the coordinator serializes
    them. This asserts the lock path: final coordinator.data has all four
    LEDs coloured, and each POST carried the cumulative payload.
    """
    import asyncio

    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status_leds_off)
    coord = entry.runtime_data

    colors = [[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0]]
    expected_hex = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00"]

    sent_payloads: list[list[dict]] = []

    async def _fake_post(self_client, leds):  # noqa: ARG001
        # Mimic the real device's ~260 ms POST latency so two calls overlap
        # in time — if the lock doesn't hold, call B will have read state
        # before call A's optimistic updates.
        sent_payloads.append([dict(led) for led in leds])
        await asyncio.sleep(0.15)

    with patch.object(BtclockClient, "async_set_lights", new=_fake_post):

        async def _toggle(i: int, rgb: list[int]) -> None:
            await hass.services.async_call(
                "light",
                "turn_on",
                {"entity_id": f"light.btclock_9d5530_led_{i + 1}", "rgb_color": rgb},
                blocking=True,
            )

        # Fire all four within 150 ms (less than one POST's latency), so they
        # would all be in flight concurrently without the lock.
        tasks = []
        for i, rgb in enumerate(colors):
            tasks.append(hass.async_create_task(_toggle(i, rgb)))
            await asyncio.sleep(0.05)
        await asyncio.gather(*tasks)

    # All four LEDs end up coloured.
    final = coord.data["leds"]
    assert [led["hex"] for led in final] == expected_hex

    # Each successive POST carried the accumulated state: the i-th call
    # must contain LEDs 0..i coloured and i+1..3 still off.
    assert len(sent_payloads) == 4
    for i, payload in enumerate(sent_payloads):
        for j in range(4):
            expected = expected_hex[j] if j <= i else "#000000"
            assert payload[j]["hex"] == expected, (
                f"call {i} LED {j}: expected {expected}, got {payload[j]['hex']}"
            )


async def _fake_post_with_latency(latency_s: float, sent: list[list[dict]]):
    """Helper: return a fake POST that records payloads and sleeps."""
    import asyncio

    async def _post(_client, leds):
        sent.append([dict(led) for led in leds])
        await asyncio.sleep(latency_s)

    return _post


async def test_same_led_rapid_toggle_ends_correctly(
    hass: HomeAssistant, load_fixture, status_leds_off
) -> None:
    """Rapid on→off→on on the same LED: final state is on, payloads are
    coherent, and the middle off-state isn't lost as a zombie value."""
    import asyncio

    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status_leds_off)
    coord = entry.runtime_data

    sent: list[list[dict]] = []
    with patch.object(
        BtclockClient,
        "async_set_lights",
        new=await _fake_post_with_latency(0.15, sent),
    ):
        tasks = [
            hass.async_create_task(
                hass.services.async_call(
                    "light",
                    "turn_on",
                    {
                        "entity_id": "light.btclock_9d5530_led_1",
                        "rgb_color": [255, 0, 0],
                    },
                    blocking=True,
                )
            )
        ]
        await asyncio.sleep(0.05)
        tasks.append(
            hass.async_create_task(
                hass.services.async_call(
                    "light",
                    "turn_off",
                    {"entity_id": "light.btclock_9d5530_led_1"},
                    blocking=True,
                )
            )
        )
        await asyncio.sleep(0.05)
        tasks.append(
            hass.async_create_task(
                hass.services.async_call(
                    "light",
                    "turn_on",
                    {
                        "entity_id": "light.btclock_9d5530_led_1",
                        "rgb_color": [0, 0, 255],
                    },
                    blocking=True,
                )
            )
        )
        await asyncio.gather(*tasks)

    # Each call saw the previous call's optimistic state.
    assert len(sent) == 3
    assert [p[0]["hex"] for p in sent] == ["#FF0000", "#000000", "#0000FF"]
    # Final state is blue-on.
    assert coord.data["leds"][0]["hex"] == "#0000FF"


async def test_mixed_on_off_interleaved(hass: HomeAssistant, load_fixture) -> None:
    """LEDs 0/2 are already on; toggle 0 off, 1 on, 2 off, 3 on back-to-back.
    Final state must reflect every intended change."""
    import asyncio

    status = load_fixture("status_v3_4_revb").copy()
    status["leds"] = [
        {"hex": "#FF0000", "red": 255, "green": 0, "blue": 0},
        {"hex": "#000000", "red": 0, "green": 0, "blue": 0},
        {"hex": "#00FF00", "red": 0, "green": 255, "blue": 0},
        {"hex": "#000000", "red": 0, "green": 0, "blue": 0},
    ]
    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status)
    coord = entry.runtime_data

    sent: list[list[dict]] = []
    with patch.object(
        BtclockClient,
        "async_set_lights",
        new=await _fake_post_with_latency(0.15, sent),
    ):

        async def call(service: str, index: int, rgb: list[int] | None = None) -> None:
            data = {"entity_id": f"light.btclock_9d5530_led_{index + 1}"}
            if rgb is not None:
                data["rgb_color"] = rgb
            await hass.services.async_call("light", service, data, blocking=True)

        tasks = []
        for op in [
            ("turn_off", 0, None),
            ("turn_on", 1, [0, 0, 255]),
            ("turn_off", 2, None),
            ("turn_on", 3, [255, 255, 0]),
        ]:
            tasks.append(hass.async_create_task(call(*op)))
            await asyncio.sleep(0.05)
        await asyncio.gather(*tasks)

    # Walk the payload tape: each entry must match the running expected state.
    expected_progression = [
        ["#000000", "#000000", "#00FF00", "#000000"],  # LED 0 off
        ["#000000", "#0000FF", "#00FF00", "#000000"],  # LED 1 on (blue)
        ["#000000", "#0000FF", "#000000", "#000000"],  # LED 2 off
        ["#000000", "#0000FF", "#000000", "#FFFF00"],  # LED 3 on (yellow)
    ]
    assert [[p["hex"] for p in payload] for payload in sent] == expected_progression

    assert [led["hex"] for led in coord.data["leds"]] == [
        "#000000",
        "#0000FF",
        "#000000",
        "#FFFF00",
    ]


async def test_rgb_color_sequence_on_same_led(
    hass: HomeAssistant, load_fixture, status_leds_off
) -> None:
    """LED 0: red → green → blue in rapid succession. Final colour is blue;
    each intermediate POST carries the color that was current at call time."""
    import asyncio

    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status_leds_off)
    coord = entry.runtime_data

    sent: list[list[dict]] = []
    with patch.object(
        BtclockClient,
        "async_set_lights",
        new=await _fake_post_with_latency(0.15, sent),
    ):
        tasks = []
        for rgb in ([255, 0, 0], [0, 255, 0], [0, 0, 255]):
            tasks.append(
                hass.async_create_task(
                    hass.services.async_call(
                        "light",
                        "turn_on",
                        {
                            "entity_id": "light.btclock_9d5530_led_1",
                            "rgb_color": rgb,
                        },
                        blocking=True,
                    )
                )
            )
            await asyncio.sleep(0.05)
        await asyncio.gather(*tasks)

    assert [p[0]["hex"] for p in sent] == ["#FF0000", "#00FF00", "#0000FF"]
    assert coord.data["leds"][0] == {
        "hex": "#0000FF",
        "red": 0,
        "green": 0,
        "blue": 255,
    }


async def test_sse_frame_during_led_write_is_reconciled_after(
    hass: HomeAssistant, load_fixture, status_leds_off
) -> None:
    """An SSE frame arriving mid-write sets the baseline, but the optimistic
    update fired after the POST returns is what the UI ends up on."""
    import asyncio

    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status_leds_off)
    coord = entry.runtime_data

    post_entered = asyncio.Event()

    async def slow_post(_client, _leds):
        post_entered.set()
        await asyncio.sleep(0.2)

    with patch.object(BtclockClient, "async_set_lights", new=slow_post):
        write_task = hass.async_create_task(
            hass.services.async_call(
                "light",
                "turn_on",
                {
                    "entity_id": "light.btclock_9d5530_led_1",
                    "rgb_color": [255, 128, 0],
                },
                blocking=True,
            )
        )
        await post_entered.wait()
        # Simulate a stale SSE frame landing mid-write with LEDs all off.
        await coord._on_status_frame(  # noqa: SLF001
            {"leds": [{"hex": "#000000"} for _ in range(4)]}
        )
        # Optimistic update fires after the fake POST completes and wins.
        await write_task

    assert coord.data["leds"][0]["hex"] == "#FF8000"


async def test_burst_of_writes_preserves_all(
    hass: HomeAssistant, load_fixture, status_leds_off
) -> None:
    """Fire 12 back-to-back LED writes across 4 LEDs; every LED ends with
    the last colour requested for it and no payload ever regressed state."""
    import asyncio

    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status_leds_off)
    coord = entry.runtime_data

    operations = [
        (0, [255, 0, 0]),
        (1, [0, 255, 0]),
        (0, [255, 255, 0]),
        (2, [0, 0, 255]),
        (1, [255, 0, 255]),
        (3, [0, 255, 255]),
        (0, [255, 255, 255]),
        (2, [128, 128, 128]),
        (3, [64, 64, 64]),
        (1, [0, 0, 0]),  # LED 1 off via turn_off path would be cleaner;
        # turn_on with (0,0,0) is bumped to white, so use off.
    ]

    async def do(i: int, rgb: list[int]) -> None:
        if rgb == [0, 0, 0]:
            await hass.services.async_call(
                "light",
                "turn_off",
                {"entity_id": f"light.btclock_9d5530_led_{i + 1}"},
                blocking=True,
            )
        else:
            await hass.services.async_call(
                "light",
                "turn_on",
                {
                    "entity_id": f"light.btclock_9d5530_led_{i + 1}",
                    "rgb_color": rgb,
                },
                blocking=True,
            )

    sent: list[list[dict]] = []
    with patch.object(
        BtclockClient,
        "async_set_lights",
        new=await _fake_post_with_latency(0.05, sent),
    ):
        tasks = []
        for i, rgb in operations:
            tasks.append(hass.async_create_task(do(i, rgb)))
            await asyncio.sleep(0.02)
        await asyncio.gather(*tasks)

    # Compute the expected final state from the operation sequence.
    expected = [[0, 0, 0] for _ in range(4)]
    for i, rgb in operations:
        expected[i] = rgb
    expected_hex = ["#{:02X}{:02X}{:02X}".format(*c) for c in expected]
    expected_hex[1] = "#000000"  # last op set LED 1 off

    assert [led["hex"] for led in coord.data["leds"]] == expected_hex
    assert len(sent) == len(operations)
    # No payload ever reverted a previously-set LED: each payload must be a
    # superset-or-equal of the previous payload's non-off LEDs for indices
    # not touched by the current operation.
    for call_idx in range(1, len(sent)):
        prev = sent[call_idx - 1]
        curr = sent[call_idx]
        touched = operations[call_idx][0]
        for j in range(4):
            if j == touched:
                continue
            assert curr[j]["hex"] == prev[j]["hex"], (
                f"call {call_idx} leaked previous LED {j}: "
                f"{prev[j]['hex']} → {curr[j]['hex']}"
            )


async def test_screen_select_optimistic(hass: HomeAssistant, load_fixture) -> None:
    status = load_fixture("status_v3_4_revb").copy()
    status["currentScreen"] = 0
    entry = await _setup(hass, load_fixture("settings_v3_4_revb"), status)
    coord = entry.runtime_data

    with (
        patch.object(BtclockClient, "async_set_screen", new=AsyncMock()),
        patch.object(coord, "async_request_refresh") as refresh_mock,
    ):
        await hass.services.async_call(
            "select",
            "select_option",
            {
                "entity_id": "select.btclock_9d5530_screen",
                "option": "Market cap",
            },
            blocking=True,
        )

    refresh_mock.assert_not_called()
    assert coord.data["currentScreen"] == 1
