"""Config flow tests — happy path, auth required, reauth, zeroconf, reconfigure."""

from __future__ import annotations

from ipaddress import ip_address
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.btclock.api import BtclockAuthError, BtclockCommunicationError
from custom_components.btclock.const import DOMAIN

_TARGET = "custom_components.btclock.config_flow.BtclockClient"


async def _start_user_flow(hass: HomeAssistant, settings: dict) -> dict:
    with patch(f"{_TARGET}.async_load_settings", return_value=settings):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "btclock-9d5530.local"}
        )


async def test_user_happy_path(hass: HomeAssistant, load_fixture) -> None:
    settings = load_fixture("settings_v3_4_revb")
    result = await _start_user_flow(hass, settings)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "btclock-9d5530.local"}
    assert result["title"] == settings["hostname"]


async def test_user_flow_auth_required_then_ok(
    hass: HomeAssistant, load_fixture
) -> None:
    authed = load_fixture("settings_v3_4_authed")

    with patch(f"{_TARGET}.async_load_settings", side_effect=BtclockAuthError("401")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "btclock-9d5530.local"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "credentials"

    with patch(f"{_TARGET}.async_load_settings", return_value=authed):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "btclock", CONF_PASSWORD: "hunter2"},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_USERNAME] == "btclock"
    assert result["data"][CONF_PASSWORD] == "hunter2"


async def test_user_flow_connection_error(hass: HomeAssistant) -> None:
    with patch(
        f"{_TARGET}.async_load_settings",
        side_effect=BtclockCommunicationError("down"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "offline.local"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_zeroconf_discovery_then_confirm(
    hass: HomeAssistant, load_fixture
) -> None:
    info = ZeroconfServiceInfo(
        ip_address=ip_address("192.168.20.97"),
        ip_addresses=[ip_address("192.168.20.97")],
        hostname="btclock-9d5530.local.",
        name="btclock-9d5530._http._tcp.local.",
        port=80,
        type="_http._tcp.local.",
        properties={},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=info
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    with patch(
        f"{_TARGET}.async_load_settings",
        return_value=load_fixture("settings_v3_4_revb"),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_zeroconf_duplicate_aborts(hass: HomeAssistant, load_fixture) -> None:
    existing = MockConfigEntry(
        domain=DOMAIN,
        unique_id="btclock-9d5530",
        data={CONF_HOST: "btclock-9d5530.local"},
    )
    existing.add_to_hass(hass)

    info = ZeroconfServiceInfo(
        ip_address=ip_address("192.168.20.97"),
        ip_addresses=[ip_address("192.168.20.97")],
        hostname="btclock-9d5530.local.",
        name="btclock-9d5530._http._tcp.local.",
        port=80,
        type="_http._tcp.local.",
        properties={},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=info
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(hass: HomeAssistant, load_fixture) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="btclock-9d5530",
        data={CONF_HOST: "btclock-9d5530.local", CONF_USERNAME: "btclock"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        f"{_TARGET}.async_load_settings",
        return_value=load_fixture("settings_v3_4_authed"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "btclock", CONF_PASSWORD: "newpass"},
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "newpass"


async def test_reconfigure_host_change(hass: HomeAssistant, load_fixture) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="btclock-9d5530",
        data={CONF_HOST: "192.168.20.97"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    with patch(
        f"{_TARGET}.async_load_settings",
        return_value=load_fixture("settings_v3_4_revb"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "btclock-9d5530.local"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "btclock-9d5530.local"
