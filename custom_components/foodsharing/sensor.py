"""Foodsharing.de sensor platform."""
from datetime import datetime, timedelta
import logging
import re
import json
from typing import Any, Callable, Dict, Optional

import async_timeout

from homeassistant import config_entries, core
from homeassistant.helpers import aiohttp_client
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import ATTR_ATTRIBUTION
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)
import voluptuous as vol

from .const import (
    ATTRIBUTION,
    CONF_LATITUDE,
    ATTR_ID,
    ATTR_DESCRIPTION,
    ATTR_UNTIL,

    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
# Time between updating data
SCAN_INTERVAL = timedelta(minutes=10)

COUNTY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LATITUDE): cv.string,
    }
)

async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    """Setup sensors from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    # Update our config to include new repos and remove those that have been removed.
    if config_entry.options:
        config.update(config_entry.options)
    sensors = [FoodsharingSensor(config[CONF_LATITUDE], hass)]
    async_add_entities(sensors, update_before_add=True)


async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: Callable,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the sensor platform."""
    sensors = [FoodsharingSensor(config[CONF_LATITUDE], hass)]
    async_add_entities(sensors, update_before_add=True)


class FoodsharingSensor(Entity):
    """Collects and represents foodsharing baskets based on given coordinates"""

    def __init__(self, latitude: str, hass: HomeAssistantType):
        super().__init__()
        self.latitude = latitude
        self.hass = hass
        self.attrs: Dict[str, Any] = {CONF_LATITUDE: self.latitude}
        self.updated = datetime.now()
        self._name = f"Foodsharing {latitude}"
        self._state = None
        self._available = True

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        #return self._name
        return f"Foodsharing-{self.latitude}"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
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
        """Return extra attributes."""
        return self.attrs

    async def async_update(self):
        #_LOGGER.debug(f"HA Parameters: 'email':'{self.email}', 'password':'HIDDEN', 'lat':'{self.latitude}', 'long':'{self.longitude}', 'distance':'{self.distance}'")
        try:
            with async_timeout.timeout(30):
                json_parameters = {'email':'{self.email}', 'password':'{self.password}', 'remember_me':'true'}
                url_login = 'https://foodsharing.de/api/user/login'
                #headers = {'Content-Type: application/json'}
                response_login = await aiohttp_client.async_get_clientsession(self.hass).post(url_login, json=json_parameters)

                _LOGGER.debug(f"Login: '{response_login.status}' {response_login.text} - {response_login.headers}")

                if response_login.status == 400:
                    _LOGGER.info(f"Bad request. Most likely because you are already signed in and cant sign in twice. Or json credentials were missing. Continuing... - '{response_login.text}'")
                elif response_login.status == 405:
                    _LOGGER.exception(f"Invalid request. Please report this issue to the developer. '{response_login.text}'")
                elif not response_login.status == 200:
                    _LOGGER.exception(f"Error '{response_login.status}' - Invalid login credentials! - {response_login.text}")
        except:
            self._available = False
            _LOGGER.exception(f"Unable to login for '{self.latitude}'")
        try:
            with async_timeout.timeout(30):
                url = 'https://foodsharing.de/api/baskets/nearby?lat={self.latitude}&lon={self.longitude}&distance={self.distance}'
                
                #params = {'lat': '{self.latitude}', 'lon': '{self.longitude}', 'distance': '{self.distance}'}
                #response = await aiohttp_client.async_get_clientsession(self.hass).get(url, params=params)
                #expect = 'https://foodsharing.de/api/baskets/nearby?lat=value1&lon=value2&distance=value3'

                response = await aiohttp_client.async_get_clientsession(self.hass).get(url)

                _LOGGER.debug(f"Getting Baskets: '{response.status}' {response.text} - {response_login.headers}")
                _LOGGER.debug(f"Fetching URL: '{url}")

                if response.status == 200:
                    raw_html = await response.text()
                    json_data = json.loads(raw_html)

                    # Doesnt work due to: TypeError: the JSON object must be str, bytes or bytearray, not dict
                    #json_response = await response.json()
                    #json_data = json.loads(json_response)

                    _LOGGER.debug(f"JSON Response: '{json_data}")
                
                    baskets_count = len(json_data['baskets'])

                    if baskets_count > 0:
                        _LOGGER.debug(f"JSON first basket id: '{json_data['baskets'][0]['id']}'")
                        self.attrs[ATTR_ID] = json_data['baskets'][0]['id'],
                        self.attrs[ATTR_DESCRIPTION] = json_data['baskets'][0]['description'],
                        self.attrs[ATTR_UNTIL] = json_data['baskets'][0]['until']

                    self.attrs[ATTR_ATTRIBUTION] = f"last updated {self.updated.strftime('%d %b, %Y  %H:%M:%S')} \n{ATTRIBUTION}"
                    self._state = baskets_count
                    self._available = True
                elif response.status == 401:
                    self._available = False
                    _LOGGER.exception(f"Not authentificated! Maybe wrong login credentials? Cannot fetch data.")
                elif response.status == 405:
                    self._available = False
                    _LOGGER.exception(f"Invalid request. Please report this issue to the developer. - '{response.text}'")
                else:
                    self._available = False
                    _LOGGER.exception(f"Error '{response.status}' - Cannot retrieve data for: '{self.latitude}'")
        except:
            self._available = False
            _LOGGER.exception(f"Cannot retrieve data for: '{self.latitude}'")