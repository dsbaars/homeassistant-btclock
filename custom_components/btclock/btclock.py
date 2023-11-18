"""BTClock client."""
import aiohttp
import async_timeout

class BtclockClientError(Exception):
    """Exception to indicate a general API error."""

class Btclock:
    """BTClock client."""

    def __init__(self, host, session: aiohttp.ClientSession):
        """BTClock client."""
        self._host = host
        self._session = session
        self._status_data = None
        self._settings_data = None

    async def load_settings(self):
        """Get settings from API."""

        response = await self._api_wrapper(
            method="get",
            url=f"http://{self._host}/api/settings",
            headers={"Content-type": "application/json; charset=UTF-8"},
        )
        self._settings_data = response


    async def update_status(self):
        """Update status from API."""

        response = await self._api_wrapper(
            method="get",
            url=f"http://{self._host}/api/status",
            headers={"Content-type": "application/json; charset=UTF-8"},
        )
        self._status_data = response

    def get_screens(self):
        """Get screen id mapping from API."""
        key_value_map = {}

        for screen in self._settings_data.get('screens'):
            # Assuming "id" is the key and "name" is the value, you can modify this based on your JSON structure
            key = screen["id"]
            value = screen["name"]

            # Add the key-value pair to the dictionary
            key_value_map[key] = value

        return key_value_map


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

    async def async_light_on(self, key, value: str = "FFCC00") -> any:
        """Get data from the API."""

        newLeds = [{"hex": led.get("hex")} for led in self._status_data.get('leds')]
        newLeds[key]["hex"] = f'#{value}'

        return await self._api_wrapper(
            method="patch",
            url=f"http://{self._host}/api/lights",
            headers={'Content-Type': 'application/json'},
            data=newLeds,
            expect_json=False
        )

    async def async_light_off(self, key) -> any:
        """Get data from the API."""
        return await self.async_light_on(key, "000000")

    async def async_set_screen(self, value) -> any:
        """Get data from the API."""
        return await self._api_wrapper(
            method="get",
            url=f"http://{self._host}/api/show/screen/{value}",
            expect_json=False
        )



    async def async_timer_start(self) -> any:
        """Get data from the API."""
        return await self._api_wrapper(
            method="get",
            url=f"http://{self._host}/api/action/timer_restart",
            expect_json=False
        )

    async def async_timer_stop(self) -> any:
        """Get data from the API."""
        return await self._api_wrapper(
            method="get",
            url=f"http://{self._host}/api/action/pause",
            expect_json=False
        )

    async def _api_wrapper(
            self,
            method: str,
            url: str,
            data: dict | None = None,
            headers: dict | None = None,
            expect_json: bool = True
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
                        raise BtclockClientError(
                            "Invalid credentials",
                        )
                    response.raise_for_status()
                    if expect_json:
                        return await response.json()
                    else:
                        return
            except Exception as exception:  # pylint: disable=broad-except
                raise BtclockClientError(
                    "Something really wrong happened!"
                ) from exception
