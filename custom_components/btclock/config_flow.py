"""Config flow for BTClock."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import (
    BtclockAuthError,
    BtclockClient,
    BtclockCommunicationError,
    BtclockError,
)
from .const import DOMAIN, LOGGER


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


class BtclockConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle BTClock config, reauth, and reconfigure flows."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._hostname: str | None = None  # from /api/settings

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
                return await self._finish_create()

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
        self._host = hostname
        self._hostname = short

        await self.async_set_unique_id(short)
        self._abort_if_unique_id_configured(updates={CONF_HOST: hostname})
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
        return await self._finish_create()

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
            else:
                return await self._finish_create()

        return self.async_show_form(
            step_id="credentials",
            data_schema=_credentials_schema(
                {CONF_USERNAME: self._username} if self._username else None
            ),
            errors=errors,
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
                await self.async_set_unique_id(
                    self._hostname or entry.unique_id, raise_on_progress=False
                )
                self._abort_if_unique_id_mismatch(reason="another_device")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_HOST: self._host},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema({CONF_HOST: entry.data[CONF_HOST]}),
            errors=errors,
        )

    # ---- internals ---------------------------------------------------------

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
        return "ok"

    async def _finish_create(self) -> ConfigFlowResult:
        """Shared happy-path: set unique_id + create the entry."""
        assert self._host is not None
        unique_id = self._hostname or self._host
        # For user flow we haven't set unique_id yet; for zeroconf it's already set
        # but calling again with raise_on_progress=False is fine.
        if self.source not in (SOURCE_REAUTH, SOURCE_RECONFIGURE):
            await self.async_set_unique_id(unique_id, raise_on_progress=False)
            self._abort_if_unique_id_configured(updates={CONF_HOST: self._host})

        data: dict[str, Any] = {CONF_HOST: self._host}
        if self._username is not None:
            data[CONF_USERNAME] = self._username
            data[CONF_PASSWORD] = self._password
        return self.async_create_entry(title=unique_id, data=data)
