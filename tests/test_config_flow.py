"""Config flow tests — happy path, auth required, reauth, zeroconf, reconfigure, options."""

from __future__ import annotations

from ipaddress import ip_address
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant.common import MockConfigEntry

from custom_components.btclock.api import BtclockAuthError, BtclockCommunicationError
from custom_components.btclock.const import (
    CONF_UPDATE_MODE,
    DOMAIN,
    UPDATE_MODE_EVENTS,
    UPDATE_MODE_POLLING,
)

_TARGET = "custom_components.btclock.config_flow.BtclockClient"
_DEFAULT_UPDATE_CHOICE = {CONF_UPDATE_MODE: UPDATE_MODE_EVENTS, CONF_SCAN_INTERVAL: 30}


@pytest.fixture(autouse=True)
def _no_entry_setup():
    """Flows here create/reload entries; don't let HA really set them up.

    With an IP host the real setup would open a socket to the device.
    Setup itself is covered in test_setup.py.
    """
    with patch("custom_components.btclock.async_setup_entry", return_value=True):
        yield


async def _advance_to_update_mode(
    hass: HomeAssistant, settings: dict, host: str = "btclock-9d5530.local"
) -> dict:
    with patch(f"{_TARGET}.async_load_settings", return_value=settings):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: host}
        )


async def test_user_happy_path(hass: HomeAssistant, load_fixture) -> None:
    settings = load_fixture("settings_v3_4_revb")
    result = await _advance_to_update_mode(hass, settings)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "update_mode"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _DEFAULT_UPDATE_CHOICE
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # The .local name the user typed is swapped for the IP the device reports.
    assert result["data"] == {CONF_HOST: settings["ip"]}
    assert result["options"] == _DEFAULT_UPDATE_CHOICE
    assert result["title"] == settings["hostname"]


async def test_user_flow_polling_mode(hass: HomeAssistant, load_fixture) -> None:
    settings = load_fixture("settings_v3_4_revb")
    result = await _advance_to_update_mode(hass, settings)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_UPDATE_MODE: UPDATE_MODE_POLLING, CONF_SCAN_INTERVAL: 15},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {
        CONF_UPDATE_MODE: UPDATE_MODE_POLLING,
        CONF_SCAN_INTERVAL: 15,
    }


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
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "update_mode"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _DEFAULT_UPDATE_CHOICE
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
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "update_mode"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _DEFAULT_UPDATE_CHOICE
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "192.168.20.97"}
    assert result["result"].unique_id == "btclock-9d5530"


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
            result["flow_id"], {CONF_HOST: "btclock-9d5530.example.lan"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    # A regular DNS name is stored as entered.
    assert entry.data[CONF_HOST] == "btclock-9d5530.example.lan"


# ---- stored address: IP instead of .local -------------------------------------


def _zeroconf_info(*addresses: str) -> ZeroconfServiceInfo:
    ips = [ip_address(a) for a in addresses]
    return ZeroconfServiceInfo(
        ip_address=ips[0],
        ip_addresses=ips,
        hostname="btclock-9d5530.local.",
        name="btclock-9d5530._http._tcp.local.",
        port=80,
        type="_http._tcp.local.",
        properties={},
    )


async def _create_via_zeroconf(
    hass: HomeAssistant, info: ZeroconfServiceInfo, settings: dict
) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=info
    )
    with patch(f"{_TARGET}.async_load_settings", return_value=settings):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], _DEFAULT_UPDATE_CHOICE
    )


async def test_zeroconf_prefers_ipv4_over_ipv6(
    hass: HomeAssistant, load_fixture
) -> None:
    info = _zeroconf_info("fe80::1", "192.168.20.97")
    result = await _create_via_zeroconf(hass, info, load_fixture("settings_v3_4_revb"))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "192.168.20.97"}


async def test_zeroconf_link_local_only_uses_device_reported_ip(
    hass: HomeAssistant, load_fixture
) -> None:
    """No usable advertised IPv4: probe the .local name, keep the reported IP."""
    info = _zeroconf_info("169.254.10.20")
    result = await _create_via_zeroconf(hass, info, load_fixture("settings_v3_4_revb"))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "192.168.20.97"}


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        # .local and IP entries follow the rediscovered address.
        ("btclock-9d5530.local", "192.168.20.97"),
        ("192.168.20.50", "192.168.20.97"),
        # A DNS name the user picked is left alone.
        ("btclock.example.lan", "btclock.example.lan"),
    ],
)
async def test_zeroconf_rediscovery_updates_stored_ip(
    hass: HomeAssistant, stored: str, expected: str
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="btclock-9d5530", data={CONF_HOST: stored}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=_zeroconf_info("192.168.20.97")
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == expected


@pytest.mark.parametrize(
    ("entered", "reported_ip", "expected"),
    [
        ("btclock-9d5530.local", "192.168.20.97", "192.168.20.97"),
        ("btclock-9d5530.local.", "192.168.20.97", "192.168.20.97"),
        ("192.168.20.97", "192.168.20.97", "192.168.20.97"),
        ("btclock.example.lan", "192.168.20.97", "btclock.example.lan"),
        # The device reports no usable IP: keep what the user typed.
        ("btclock-9d5530.local", "0.0.0.0", "btclock-9d5530.local"),
        ("btclock-9d5530.local", None, "btclock-9d5530.local"),
    ],
)
async def test_user_flow_stored_host(
    hass: HomeAssistant, load_fixture, entered: str, reported_ip, expected: str
) -> None:
    settings = load_fixture("settings_v3_4_revb")
    if reported_ip is None:
        settings.pop("ip")
    else:
        settings["ip"] = reported_ip
    result = await _advance_to_update_mode(hass, settings, host=entered)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _DEFAULT_UPDATE_CHOICE
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: expected}


async def test_reconfigure_local_name_stores_ip(
    hass: HomeAssistant, load_fixture
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="btclock-9d5530", data={CONF_HOST: "192.168.20.50"}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    with patch(
        f"{_TARGET}.async_load_settings",
        return_value=load_fixture("settings_v3_4_revb"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "btclock-9d5530.local"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "192.168.20.97"


async def test_reconfigure_onto_auth_device_updates_existing_entry(
    hass: HomeAssistant, load_fixture
) -> None:
    """Reconfigure -> credentials must update the entry, not create a second one."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="btclock-9d5530", data={CONF_HOST: "192.168.20.50"}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    with patch(f"{_TARGET}.async_load_settings", side_effect=BtclockAuthError("401")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "btclock-9d5530.local"}
        )
    assert result["step_id"] == "credentials"
    with patch(
        f"{_TARGET}.async_load_settings",
        return_value=load_fixture("settings_v3_4_authed"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "btclock", CONF_PASSWORD: "hunter2"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert entry.data == {
        CONF_HOST: "192.168.20.97",
        CONF_USERNAME: "btclock",
        CONF_PASSWORD: "hunter2",
    }


async def test_options_flow_changes_update_mode(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="btclock-9d5530",
        data={CONF_HOST: "btclock-9d5530.local"},
        options={CONF_UPDATE_MODE: UPDATE_MODE_EVENTS, CONF_SCAN_INTERVAL: 30},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_UPDATE_MODE: UPDATE_MODE_POLLING, CONF_SCAN_INTERVAL: 60},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_UPDATE_MODE] == UPDATE_MODE_POLLING
    assert entry.options[CONF_SCAN_INTERVAL] == 60
