"""Foodsharing.de sensor platform."""
from datetime import datetime, timedelta
import logging
import json
from typing import Any, Dict, Optional

import async_timeout
from homeassistant import config_entries, core
from homeassistant.helpers import aiohttp_client
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import ATTR_ATTRIBUTION
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTRIBUTION,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_LATITUDE_FS,
    CONF_LONGITUDE_FS,
    CONF_DISTANCE,
    ATTR_BASKETS,
    ATTR_ID,
    ATTR_DESCRIPTION,
    ATTR_UNTIL,
    ATTR_PICTURE,
    ATTR_ADDRESS,
    ATTR_MAPS_LINK,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=120)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigType, async_add_entities
):
    """Setup sensors from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug("Sensor async_setup_entry")

    if entry.options:
        config.update(entry.options)

    sensor = FoodsharingSensor(config, hass)
    async_add_entities([sensor], update_before_add=True)

class FoodsharingSensor(Entity):
    """Collects and represents foodsharing baskets based on given coordinates."""

    def __init__(self, config, hass: HomeAssistant):
        super().__init__()

        self.email = config[CONF_EMAIL]
        self.password = config[CONF_PASSWORD]
        self.latitude_fs = config[CONF_LATITUDE_FS]
        self.longitude_fs = config[CONF_LONGITUDE_FS]
        self.distance = config[CONF_DISTANCE]
        self.hass = hass
        self.attrs: Dict[str, Any] = {CONF_LONGITUDE_FS: self.longitude_fs}
        self.updated = datetime.now()
        self._name = f"Foodsharing {self.latitude_fs}"
        self._state = None
        self._available = True

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return f"Foodsharing-{self.latitude_fs}"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        _LOGGER.debug(f"Sensor available: {self._available}")
        return self._available

    @property
    def icon(self) -> str:
        return "mdi:basket-unfill"

    @property
    def state(self) -> Optional[str]:
        if self._state is not None:
            return self._state
        else:
            return "Error"

    @property
    def unit_of_measurement(self):
        """Return unit of measurement."""
        return "baskets"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        _LOGGER.debug(f"Extra state attributes: {self.attrs}")
        return self.attrs

    async def async_update(self):
        """Fetch data from the Foodsharing API."""
        try:
            with async_timeout.timeout(30):
                NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
                url = f'https://foodsharing.de/api/baskets/nearby?lat={self.latitude_fs}&lon={self.longitude_fs}&distance={self.distance}'

                session = aiohttp_client.async_get_clientsession(self.hass)
                _LOGGER.debug(f"Fetching URL: '{url}'")
                response = await session.get(url)
                _LOGGER.debug(f"Getting Baskets: Status: {response.status}, Headers: {response.headers}")

                if response.status == 200:
                    raw_html = await response.text()
                    json_data = json.loads(raw_html)
                    _LOGGER.debug(f"JSON Response: '{json_data}'")

                    baskets = await self._process_baskets(json_data, NOMINATIM_URL)
                    baskets_count = len(baskets)
                    _LOGGER.debug(f"Processed baskets count: {baskets_count}")
                    _LOGGER.debug(f"Baskets Data: {baskets}")

                    self.attrs[ATTR_BASKETS] = baskets
                    self.attrs[ATTR_ATTRIBUTION] = f"last updated {datetime.now()} \n{ATTRIBUTION}"
                    _LOGGER.debug(f"Attributes: {self.attrs}")

                    self._state = baskets_count
                    self._available = True
                    _LOGGER.debug(f"Sensor state set to: {self._state}")

                elif response.status == 401:
                    _LOGGER.info("Received 401 Unauthorized. Attempting to re-authenticate.")
                    await self._perform_login_and_retry(session, url)

                elif response.status == 503:
                    _LOGGER.error("Error 503 - Cannot reach Foodsharing API. The API might be under maintenance.")
                    self._available = False

                else:
                    _LOGGER.error(f"Unexpected error: {response.status} - Cannot retrieve data.")
                    self._available = False

        except Exception as e:
            _LOGGER.error(f"Exception during update: {e}")
            self._available = False

    async def _perform_login_and_retry(self, session, url):
        """Attempt to log in and retry fetching data."""
        try:
            with async_timeout.timeout(30):
                login_payload = {'email': self.email, 'password': self.password, 'remember_me': 'true'}
                login_url = 'https://foodsharing.de/api/user/login'
                login_response = await session.post(login_url, json=login_payload)
                login_response_text = await login_response.text()
                _LOGGER.debug(f"Login response: Status: {login_response.status}, Text: {login_response_text}")

                if login_response.status == 200:
                    _LOGGER.info("Login successful. Retrying data fetch.")
                    response = await session.get(url)
                    if response.status == 200:
                        raw_html = await response.text()
                        json_data = json.loads(raw_html)
                        _LOGGER.debug(f"JSON Response after login: '{json_data}'")

                        baskets = await self._process_baskets(json_data, "https://nominatim.openstreetmap.org/reverse")
                        baskets_count = len(baskets)
                        _LOGGER.debug(f"Processed baskets count after login: {baskets_count}")

                        self.attrs[ATTR_BASKETS] = baskets
                        self.attrs[ATTR_ATTRIBUTION] = f"last updated {datetime.now()} \n{ATTRIBUTION}"
                        self._state = baskets_count
                        self._available = True
                    else:
                        _LOGGER.error(f"Error during fetch after login: {response.status}")
                        self._available = False
                else:
                    _LOGGER.error(f"Login failed: {login_response.status} - {login_response_text}")
                    self._available = False

        except Exception as e:
            _LOGGER.error(f"Exception during login: {e}")
            self._available = False

    async def _process_baskets(self, json_data, nominatim_url):
        """Process basket data and return formatted list."""
        baskets = []

        if isinstance(json_data, dict):
            baskets_data = json_data.get('baskets', [])
        elif isinstance(json_data, list):
            baskets_data = json_data
        else:
            _LOGGER.error("Unexpected json_data type: %s", type(json_data).__name__)
            return []

        _LOGGER.debug(f"Baskets Data Raw: {baskets_data}")
        if baskets_data:
            baskets_data = sorted(baskets_data, key=lambda x: x['id'], reverse=True)
            for basket in baskets_data:
                until = datetime.fromtimestamp(basket['until']).strftime('%c')
                picture = basket.get('picture', "unavailable")
                if picture != "unavailable":
                    picture = f"https://foodsharing.de{picture}"

                if 'lat' in basket and 'lon' in basket:
                    location_human_readable = await self._get_human_readable_location(basket['lat'], basket['lon'])
                    _LOGGER.debug(f"Location for basket ID {basket['id']}: {location_human_readable}")
                    maps_link = f"https://www.google.de/maps/place/{basket['lat']},{basket['lon']}"
                else:
                    _LOGGER.debug(f"Skipping location fetching for basket ID {basket['id']} due to missing 'lat' or 'lon'.")
                    location_human_readable = "Location unavailable"
                    maps_link = "Unavailable"

                basket_info = {
                    ATTR_ID: basket['id'],
                    ATTR_DESCRIPTION: basket['description'],
                    ATTR_UNTIL: until,
                    ATTR_PICTURE: picture,
                    ATTR_ADDRESS: location_human_readable,
                    ATTR_MAPS_LINK: maps_link,
                }

                _LOGGER.debug(f"Processed Basket Info: {basket_info}")
                baskets.append(basket_info)

        _LOGGER.debug(f"Final Baskets List: {baskets}")
        return baskets

    async def _get_human_readable_location(self, lat, lon):
        """Retrieve a human-readable location from Nominatim."""
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        session = aiohttp_client.async_get_clientsession(self.hass)
        try:
            _LOGGER.debug(f"Fetching location from Nominatim: '{url}'")
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.debug(f"Nominatim response: {data}")
                    if 'address' in data:
                        address = data['address']
                        location_parts = [
                            address.get('house_number', ''),
                            address.get('road', ''),
                            address.get('town', ''),
                            address.get('state', ''),
                            address.get('country', '')
                        ]
                        # Remove empty parts and concatenate the address
                        location = ", ".join(part for part in location_parts if part)
                        return location if location else "Address unavailable"
                    else:
                        _LOGGER.warning("Nominatim response has no address data.")
                        return "Address unavailable"
                else:
                    _LOGGER.warning(f"Nominatim returned status {response.status}")
                    return "Address unavailable"
        except Exception as e:
            _LOGGER.error(f"Error retrieving human-readable location: {e}")
        return "Address unavailable"
