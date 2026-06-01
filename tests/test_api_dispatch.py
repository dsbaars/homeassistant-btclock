"""Verify the API client issues the correct HTTP verb+path per variant."""

from __future__ import annotations

import re

import aiohttp
import pytest

from custom_components.btclock.api import BtclockClient, BtclockError
from custom_components.btclock.models import ApiVariant

HOST = "btclock.test"


def _expect(mock, method: str, url_re: str) -> None:
    """Register a mock response matching method+regex-URL."""
    mock.add(re.compile(url_re), method=method, status=200, payload={})


def _recorded_kwargs(mock, method: str, path: str) -> dict:
    """Return the kwargs of the last recorded request to method+path."""
    for (recorded_method, url), calls in mock.requests.items():
        if recorded_method == method and url.path == path:
            return calls[-1].kwargs
    raise AssertionError(f"no {method} {path} request was recorded")


@pytest.fixture
async def legacy_client(mock_aioresponse):
    session = aiohttp.ClientSession()
    client = BtclockClient(HOST, session)
    client._variant = ApiVariant.LEGACY  # noqa: SLF001
    yield client
    await session.close()


@pytest.fixture
async def v3_4_client(mock_aioresponse):
    session = aiohttp.ClientSession()
    client = BtclockClient(HOST, session)
    client._variant = ApiVariant.V3_4  # noqa: SLF001
    yield client
    await session.close()


@pytest.fixture
async def v4_client(mock_aioresponse):
    session = aiohttp.ClientSession()
    client = BtclockClient(HOST, session)
    client._variant = ApiVariant.V4  # noqa: SLF001
    yield client
    await session.close()


# ---- timer -------------------------------------------------------------------


async def test_legacy_timer_start_uses_get(mock_aioresponse, legacy_client) -> None:
    _expect(mock_aioresponse, "GET", rf"^http://{HOST}/api/action/timer_restart")
    await legacy_client.async_timer_start()


async def test_v3_4_timer_start_uses_post(mock_aioresponse, v3_4_client) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/action/timer_restart")
    await v3_4_client.async_timer_start()


async def test_legacy_timer_stop_uses_get(mock_aioresponse, legacy_client) -> None:
    _expect(mock_aioresponse, "GET", rf"^http://{HOST}/api/action/pause")
    await legacy_client.async_timer_stop()


async def test_v3_4_timer_stop_uses_post(mock_aioresponse, v3_4_client) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/action/pause")
    await v3_4_client.async_timer_stop()


# ---- screen ------------------------------------------------------------------


async def test_legacy_set_screen_path_param(mock_aioresponse, legacy_client) -> None:
    _expect(mock_aioresponse, "GET", rf"^http://{HOST}/api/show/screen/3")
    await legacy_client.async_set_screen(3)


async def test_v3_4_set_screen_query_param(mock_aioresponse, v3_4_client) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/show/screen\?s=3")
    await v3_4_client.async_set_screen(3)


async def test_v4_set_screen_uses_json_body(mock_aioresponse, v4_client) -> None:
    """v4 sends the screen id as a JSON body, not a `?s=` query param.

    The `$` anchor fails the match if a query string sneaks onto the URL.
    """
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/show/screen$")
    await v4_client.async_set_screen(3)
    kwargs = _recorded_kwargs(mock_aioresponse, "POST", "/api/show/screen")
    assert kwargs.get("json") == {"s": 3}
    assert kwargs.get("params") is None


async def test_v4_set_currency_uses_json_body(mock_aioresponse, v4_client) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/show/currency$")
    await v4_client.async_set_currency("EUR")
    kwargs = _recorded_kwargs(mock_aioresponse, "POST", "/api/show/currency")
    assert kwargs.get("json") == {"c": "EUR"}
    assert kwargs.get("params") is None


async def test_v3_4_set_currency_uses_query(mock_aioresponse, v3_4_client) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/show/currency\?c=EUR")
    await v3_4_client.async_set_currency("EUR")
    kwargs = _recorded_kwargs(mock_aioresponse, "POST", "/api/show/currency")
    assert kwargs.get("params") == {"c": "EUR"}
    assert kwargs.get("json") is None


async def test_v4_show_text_uses_json_body(mock_aioresponse, v4_client) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/show/text$")
    await v4_client.async_show_text("BTC")
    kwargs = _recorded_kwargs(mock_aioresponse, "POST", "/api/show/text")
    assert kwargs.get("json") == {"t": "BTC"}
    assert kwargs.get("params") is None


async def test_legacy_has_no_screen_next(mock_aioresponse, legacy_client) -> None:
    with pytest.raises(BtclockError):
        await legacy_client.async_screen_next()


async def test_v3_4_screen_next(mock_aioresponse, v3_4_client) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/screen/next")
    await v3_4_client.async_screen_next()


# ---- lights ------------------------------------------------------------------


async def test_legacy_lights_set_uses_patch(mock_aioresponse, legacy_client) -> None:
    _expect(mock_aioresponse, "PATCH", rf"^http://{HOST}/api/lights/set")
    await legacy_client.async_set_lights([{"hex": "#FFCC00"}])


async def test_v3_4_lights_set_uses_post(mock_aioresponse, v3_4_client) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/lights/set")
    await v3_4_client.async_set_lights([{"hex": "#FFCC00"}])


async def test_legacy_lights_off_uses_get(mock_aioresponse, legacy_client) -> None:
    _expect(mock_aioresponse, "GET", rf"^http://{HOST}/api/lights/off")
    await legacy_client.async_lights_off()


# ---- OTA (variant-dispatched) ----------------------------------------------


async def test_legacy_auto_update_uses_get(mock_aioresponse, legacy_client) -> None:
    """Firmware 3.3.x exposes /api/firmware/auto_update as GET, not POST.

    Live-verified on 192.168.20.253 (3.3.19) — POST returns 404, GET 200.
    """
    _expect(mock_aioresponse, "GET", rf"^http://{HOST}/api/firmware/auto_update")
    await legacy_client.async_auto_update_firmware()


async def test_v3_4_auto_update_uses_post(mock_aioresponse, v3_4_client) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/firmware/auto_update")
    await v3_4_client.async_auto_update_firmware()


async def test_v3_4_lights_off_uses_post(mock_aioresponse, v3_4_client) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/lights/off")
    await v3_4_client.async_lights_off()


async def test_v4_lights_effect_uses_post(mock_aioresponse, v4_client) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/lights/effect")
    await v4_client.async_trigger_light_effect("heartbeat")


async def test_v3_4_lights_effect_refused(mock_aioresponse, v3_4_client) -> None:
    with pytest.raises(BtclockError):
        await v3_4_client.async_trigger_light_effect("heartbeat")


async def test_v4_frontlight_set_uses_post(mock_aioresponse, v4_client) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/frontlight/set")
    await v4_client.async_set_frontlight_channels([0, 512, 1024, 2048])


async def test_v3_4_frontlight_set_refused(mock_aioresponse, v3_4_client) -> None:
    with pytest.raises(BtclockError):
        await v3_4_client.async_set_frontlight_channels([0, 512, 1024, 2048])


# ---- datasources (v4-only) ---------------------------------------------------


async def test_v4_stop_datasources_uses_post(mock_aioresponse, v4_client) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/stop_datasources")
    await v4_client.async_stop_datasources()


async def test_v3_4_stop_datasources_refused(mock_aioresponse, v3_4_client) -> None:
    with pytest.raises(BtclockError):
        await v3_4_client.async_stop_datasources()


async def test_v4_frontlight_brightness_uses_json_body(
    mock_aioresponse, v4_client
) -> None:
    """v4 dropped the legacy `?b=` query form for /api/frontlight/brightness;
    the value must travel as a JSON body or the device 400s. The `$` anchor
    fails the match if a query string sneaks onto the URL."""
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}/api/frontlight/brightness$")
    await v4_client.async_frontlight_brightness(2048)
    kwargs = _recorded_kwargs(mock_aioresponse, "POST", "/api/frontlight/brightness")
    assert kwargs.get("json") == {"b": 2048}
    assert kwargs.get("params") is None


async def test_v3_4_frontlight_brightness_uses_query(
    mock_aioresponse, v3_4_client
) -> None:
    """v3.4 firmware only reads the `?b=` query param — keep sending it."""
    _expect(
        mock_aioresponse,
        "POST",
        rf"^http://{HOST}/api/frontlight/brightness\?b=2048",
    )
    await v3_4_client.async_frontlight_brightness(2048)
    kwargs = _recorded_kwargs(mock_aioresponse, "POST", "/api/frontlight/brightness")
    assert kwargs.get("params") == {"b": 2048}
    assert kwargs.get("json") is None


# ---- new-API-only actions ----------------------------------------------------


@pytest.mark.parametrize(
    "method_name", ["async_identify", "async_restart", "async_full_refresh"]
)
async def test_new_api_actions_refused_on_legacy(
    mock_aioresponse, legacy_client, method_name
) -> None:
    with pytest.raises(BtclockError):
        await getattr(legacy_client, method_name)()


@pytest.mark.parametrize(
    "method_name, path_re",
    [
        ("async_identify", r"/api/identify"),
        ("async_restart", r"/api/restart"),
        ("async_full_refresh", r"/api/full_refresh"),
        ("async_dnd_enable", r"/api/dnd/enable"),
        ("async_dnd_disable", r"/api/dnd/disable"),
    ],
)
async def test_new_api_actions_post_on_v3_4(
    mock_aioresponse, v3_4_client, method_name: str, path_re: str
) -> None:
    _expect(mock_aioresponse, "POST", rf"^http://{HOST}{path_re}")
    await getattr(v3_4_client, method_name)()


# ---- settings patch path difference -----------------------------------------


async def test_legacy_settings_patch_uses_json_path(mock_aioresponse) -> None:
    from custom_components.btclock.api_paths import LEGACY_PATHS

    assert LEGACY_PATHS["settings_patch"] == ("PATCH", "/api/json/settings")


async def test_v3_4_settings_patch_uses_main_path() -> None:
    from custom_components.btclock.api_paths import V3_4_PATHS

    assert V3_4_PATHS["settings_patch"] == ("PATCH", "/api/settings")


# End-to-end: a settings write must hit the URL the firmware of that era
# actually registers. ≤3.3.19 serves the write on /api/json/settings (any
# method); 3.4.0+ moved it to PATCH /api/settings and dropped the json route.
# Verified against btclock_v3 webserver source at tags 3.3.19 and 3.4.0.


async def test_legacy_patch_settings_hits_json_settings(
    mock_aioresponse, legacy_client
) -> None:
    _expect(mock_aioresponse, "PATCH", rf"^http://{HOST}/api/json/settings$")
    await legacy_client.async_patch_settings({"ledBrightness": 100})
    kwargs = _recorded_kwargs(mock_aioresponse, "PATCH", "/api/json/settings")
    assert kwargs.get("json") == {"ledBrightness": 100}


async def test_v3_4_patch_settings_hits_settings(mock_aioresponse, v3_4_client) -> None:
    _expect(mock_aioresponse, "PATCH", rf"^http://{HOST}/api/settings$")
    await v3_4_client.async_patch_settings({"ledBrightness": 100})
    kwargs = _recorded_kwargs(mock_aioresponse, "PATCH", "/api/settings")
    assert kwargs.get("json") == {"ledBrightness": 100}


async def test_v4_patch_settings_hits_settings(mock_aioresponse, v4_client) -> None:
    _expect(mock_aioresponse, "PATCH", rf"^http://{HOST}/api/settings$")
    await v4_client.async_patch_settings({"ledBrightness": 100})
    kwargs = _recorded_kwargs(mock_aioresponse, "PATCH", "/api/settings")
    assert kwargs.get("json") == {"ledBrightness": 100}
