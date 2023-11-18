"""Adds config flow for BTClock."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.components import zeroconf
from homeassistant.data_entry_flow import FlowResult

from .btclock import Btclock

from .const import DOMAIN, LOGGER


class BtclockFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for BTClock."""

    def __init__(self) -> None:
        """Set up the instance."""
        self.discovery_info: dict[str, any] = {}

    VERSION = 1
    async def async_step_zeroconf(self, discovery_info: zeroconf.ZeroconfServiceInfo):
        """Handle a flow initialized by zeroconf."""

        hostname = discovery_info.hostname[:-1]
        short_hostname = hostname.removesuffix(".local")
        self._async_abort_entries_match({CONF_HOST: hostname})

        self.context["title_placeholders"] = {"hostname": short_hostname}
        self._host = hostname

        self.discovery_info.update(
            {
                CONF_HOST: hostname
            })
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, any] | None = None
    ) -> FlowResult:
        """Handle a confirmation flow initiated by zeroconf."""
        if user_input is None:
            return self.async_show_form(
                step_id="zeroconf_confirm",
                description_placeholders={"name": self.discovery_info[CONF_HOST]},
                errors={},
            )

        return self.async_create_entry(
            title=self.discovery_info[CONF_HOST],
            data=self.discovery_info,
        )

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.FlowResult:
        """Handle a flow initialized by the user."""
        _errors = {}
        if user_input is not None:
            try:
                await self._test_credentials(
                    host=user_input[CONF_HOST],
                )
            except Exception as exception:
                LOGGER.exception(exception)
            else:
                return self.async_create_entry(
                    title=user_input[CONF_HOST],
                    data=user_input,
                )

        data_schema = {
            vol.Required(
                        CONF_HOST,
                        default=(user_input or {}).get(CONF_HOST),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT
                        ),
                    )
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=_errors,
        )

    async def _test_credentials(self, host: str) -> None:
        """Validate credentials."""
        client = Btclock(
            host=host,
            session=async_create_clientsession(self.hass),
        )
        await client.update_status()
        return True
