"""Config flow for BTClock."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import (
    BtclockAuthError,
    BtclockClient,
    BtclockCommunicationError,
    BtclockError,
)
from .const import (
    CONF_UPDATE_MODE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UPDATE_MODE,
    DOMAIN,
    LOGGER,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    UPDATE_MODE_EVENTS,
    UPDATE_MODE_POLLING,
)
from .host_utils import is_auto_managed_host, is_mdns_host, usable_ipv4

_UPDATE_MODE_OPTIONS = [
    SelectOptionDict(value=UPDATE_MODE_EVENTS, label="Server-Sent Events (push)"),
    SelectOptionDict(value=UPDATE_MODE_POLLING, label="Polling"),
]


def _user_schema(defaults: Mapping[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
        }
    )


def _credentials_schema(defaults: Mapping[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_USERNAME, default=defaults.get(CONF_USERNAME, "btclock")
            ): str,
            vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
        }
    )


def _options_schema(defaults: Mapping[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_UPDATE_MODE,
                default=defaults.get(CONF_UPDATE_MODE, DEFAULT_UPDATE_MODE),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=_UPDATE_MODE_OPTIONS,
                    mode=SelectSelectorMode.LIST,
                )
            ),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=MAX_SCAN_INTERVAL,
                    step=1,
                    unit_of_measurement="s",
                )
            ),
        }
    )


class BtclockConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle BTClock config, reauth, and reconfigure flows."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._hostname: str | None = None  # from /api/settings
        self._device_ip: str | None = None  # from /api/settings `ip`

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> BtclockOptionsFlow:
        return BtclockOptionsFlow()

    # ---- user / zeroconf entry points --------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._host = user_input[CONF_HOST]
            result = await self._probe()
            if result == "auth_required":
                return await self.async_step_credentials()
            if result == "connection":
                errors["base"] = "cannot_connect"
            elif result == "unknown":
                errors["base"] = "unknown"
            else:
                return await self.async_step_update_mode()

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema({CONF_HOST: self._host} if self._host else None),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        hostname = discovery_info.hostname.rstrip(".")
        short = hostname.removesuffix(".local")
        # Store the advertised IPv4 address, not the .local name: every
        # later connect would otherwise depend on an mDNS lookup.
        ip = next((a for a in map(usable_ipv4, discovery_info.ip_addresses) if a), None)
        self._host = ip or hostname
        self._hostname = short

        await self.async_set_unique_id(short)
        # A rediscovered, already-configured device: follow its (possibly
        # new) IP, unless the user pinned the entry to their own DNS name.
        self._abort_if_unique_id_configured(updates=self._discovered_ip_updates(ip))
        self.context["title_placeholders"] = {"name": short}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="zeroconf_confirm",
                description_placeholders={"name": self._hostname or self._host or ""},
            )
        result = await self._probe()
        if result == "auth_required":
            return await self.async_step_credentials()
        if result in ("connection", "unknown"):
            return self.async_abort(reason="cannot_connect")
        return await self.async_step_update_mode()

    # ---- credentials step (used by user + zeroconf) ------------------------

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            result = await self._probe()
            if result == "auth_required":
                errors["base"] = "invalid_auth"
            elif result == "connection":
                errors["base"] = "cannot_connect"
            elif result == "unknown":
                errors["base"] = "unknown"
            elif self.source == SOURCE_RECONFIGURE:
                # Reconfigure onto a device that needs auth: update the
                # existing entry instead of creating a second one.
                return await self._finish_reconfigure()
            else:
                return await self.async_step_update_mode()

        return self.async_show_form(
            step_id="credentials",
            data_schema=_credentials_schema(
                {CONF_USERNAME: self._username} if self._username else None
            ),
            errors=errors,
        )

    # ---- update mode step --------------------------------------------------

    async def async_step_update_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick events vs polling, and the scan interval."""
        if user_input is not None:
            return await self._finish_create(user_input)

        return self.async_show_form(
            step_id="update_mode",
            data_schema=_options_schema(),
        )

    # ---- reauth ------------------------------------------------------------

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        self._host = entry_data[CONF_HOST]
        self._username = entry_data.get(CONF_USERNAME)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            result = await self._probe()
            if result == "auth_required":
                errors["base"] = "invalid_auth"
            elif result in ("connection", "unknown"):
                errors["base"] = "cannot_connect"
            else:
                entry = self._get_reauth_entry()
                return self.async_update_reload_and_abort(
                    entry,
                    data={
                        **entry.data,
                        CONF_USERNAME: self._username,
                        CONF_PASSWORD: self._password,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_credentials_schema({CONF_USERNAME: self._username}),
            errors=errors,
        )

    # ---- reconfigure -------------------------------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._username = entry.data.get(CONF_USERNAME)
            self._password = entry.data.get(CONF_PASSWORD)
            result = await self._probe()
            if result == "auth_required":
                return await self.async_step_credentials()
            if result in ("connection", "unknown"):
                errors["base"] = "cannot_connect"
            else:
                return await self._finish_reconfigure()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema({CONF_HOST: entry.data[CONF_HOST]}),
            errors=errors,
        )

    async def _finish_reconfigure(self) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        await self.async_set_unique_id(
            self._hostname or entry.unique_id, raise_on_progress=False
        )
        self._abort_if_unique_id_mismatch(reason="another_device")
        data_updates: dict[str, Any] = {CONF_HOST: self._host_to_store()}
        if self._username is not None:
            data_updates[CONF_USERNAME] = self._username
            data_updates[CONF_PASSWORD] = self._password
        return self.async_update_reload_and_abort(entry, data_updates=data_updates)

    # ---- internals ---------------------------------------------------------

    def _host_to_store(self) -> str:
        """Return the address to persist: the device's IP instead of a .local name.

        A `.local` name only resolves while mDNS works, so once the probe has
        reached the device we keep the IP it reports in `/api/settings`.
        IPs and regular DNS names are stored exactly as entered.
        """
        assert self._host is not None
        if is_mdns_host(self._host) and self._device_ip:
            return self._device_ip
        return self._host

    def _discovered_ip_updates(self, ip: str | None) -> dict[str, Any] | None:
        """Entry-data updates for a rediscovered, already-configured device."""
        if ip is None or self.unique_id is None:
            return None
        entry = self.hass.config_entries.async_entry_for_domain_unique_id(
            DOMAIN, self.unique_id
        )
        if entry is not None and not is_auto_managed_host(entry.data.get(CONF_HOST)):
            return None
        return {CONF_HOST: ip}

    async def _probe(self) -> str:
        """Try to load settings; return a short status string."""
        assert self._host is not None
        client = BtclockClient(
            host=self._host,
            session=async_create_clientsession(self.hass),
            username=self._username,
            password=self._password,
        )
        try:
            settings = await client.async_load_settings()
        except BtclockAuthError:
            return "auth_required"
        except BtclockCommunicationError as err:
            LOGGER.debug("BTClock probe failed: %s", err)
            return "connection"
        except BtclockError as err:
            LOGGER.exception("Unexpected BTClock probe error: %s", err)
            return "unknown"
        self._hostname = settings.get("hostname") or self._hostname
        self._device_ip = usable_ipv4(settings.get("ip"))
        return "ok"

    async def _finish_create(self, options_input: dict[str, Any]) -> ConfigFlowResult:
        """Shared happy-path: set unique_id + create the entry with options."""
        assert self._host is not None
        unique_id = self._hostname or self._host
        host = self._host_to_store()
        if self.source not in (SOURCE_REAUTH, SOURCE_RECONFIGURE):
            await self.async_set_unique_id(unique_id, raise_on_progress=False)
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        data: dict[str, Any] = {CONF_HOST: host}
        if self._username is not None:
            data[CONF_USERNAME] = self._username
            data[CONF_PASSWORD] = self._password

        options = {
            CONF_UPDATE_MODE: options_input[CONF_UPDATE_MODE],
            CONF_SCAN_INTERVAL: int(options_input[CONF_SCAN_INTERVAL]),
        }
        return self.async_create_entry(title=unique_id, data=data, options=options)


class BtclockOptionsFlow(OptionsFlow):
    """Let users change update mode / scan interval after install."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_UPDATE_MODE: user_input[CONF_UPDATE_MODE],
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(self.config_entry.options),
        )
