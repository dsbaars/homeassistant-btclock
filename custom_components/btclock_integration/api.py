"""Sample API Client."""
from __future__ import annotations

import asyncio
import socket

import aiohttp
import async_timeout


class BtclockApiClientError(Exception):
    """Exception to indicate a general API error."""


class BtclockApiClientCommunicationError(
    BtclockApiClientError
):
    """Exception to indicate a communication error."""


class BtclockApiClientAuthenticationError(
    BtclockApiClientError
):
    """Exception to indicate an authentication error."""


class BtclockApiClient:
    """Sample API Client."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Sample API Client."""
        self._host = host
        self._session = session

    async def async_get_data(self) -> any:
        """Get data from the API."""
        return await self._api_wrapper(
            method="get", url=f"http://{self._host}/api/status"
        )

    async def async_get_settings(self, value: str) -> any:
        """Get data from the API."""
        return await self._api_wrapper(
            method="get",
            url=f"http://{self._host}/api/settings",
            headers={"Content-type": "application/json; charset=UTF-8"},
        )

    async def async_lights_on(self, value: str = "FFCC00") -> any:
        """Get data from the API."""
        return await self._api_wrapper(
            method="get",
            url=f"http://{self._host}/api/lights/{value}"
        )

    async def async_lights_off(self) -> any:
        """Get data from the API."""
        return await self._api_wrapper(
            method="get",
            url=f"http://{self._host}/api/lights/off"
        )


    async def async_timer_start(self) -> any:
        """Get data from the API."""
        return await self._api_wrapper(
            method="get",
            url=f"http://{self._host}/api/action/timer_restart"
        )

    async def async_timer_stop(self) -> any:
        """Get data from the API."""
        return await self._api_wrapper(
            method="get",
            url=f"http://{self._host}/api/action/pause"
        )

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        data: dict | None = None,
        headers: dict | None = None,
    ) -> any:
        """Get information from the API."""
        try:
            async with async_timeout.timeout(10):
                response = await self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                )
                if response.status in (401, 403):
                    raise BtclockApiClientAuthenticationError(
                        "Invalid credentials",
                    )
                response.raise_for_status()
                return await response.json()

        except asyncio.TimeoutError as exception:
            raise BtclockApiClientCommunicationError(
                "Timeout error fetching information",
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            raise BtclockApiClientCommunicationError(
                "Error fetching information",
            ) from exception
        except Exception as exception:  # pylint: disable=broad-except
            raise BtclockApiClientError(
                "Something really wrong happened!"
            ) from exception
