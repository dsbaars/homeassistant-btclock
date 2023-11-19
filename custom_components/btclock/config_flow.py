"""Adds config flow for BTClock."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST,CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.components import zeroconf
from homeassistant.data_entry_flow import FlowResult

from .btclock import Btclock, BtclockClientCommunicationError,BtclockClientError

from .const import DOMAIN, LOGGER, DEFAULT_SCAN_INTERVAL


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
                description_placeholders={
                    CONF_HOST: self.discovery_info[CONF_HOST],
                    # CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL
                    },
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
            except BtclockClientCommunicationError as exception:
                LOGGER.error(exception)
                _errors["base"] = "connection"
            except BtclockClientError as exception:
                LOGGER.exception(exception)
                _errors["base"] = "unknown"
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
                    ),
            # vol.Required(
            #         CONF_SCAN_INTERVAL,
            #         default=DEFAULT_SCAN_INTERVAL,
            #     ):  int,

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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return BtclockOptionsFlowHandler(config_entry)

class BtclockOptionsFlowHandler(config_entries.OptionsFlow):
    """BTClock config flow options handler."""

    def __init__(self, config_entry):
        """Initialize BTClock options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, _user_input=None):
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=self.config_entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                ),
            ): int,
        }
        return self.async_show_form(step_id="user", data_schema=vol.Schema(schema))

    async def update_listener(hass, entry):
        """Handle options update."""
        await hass.config_entries.async_reload(entry.entry_id)
