"""Foodsharing.de sensor platform."""
from datetime import timedelta
import logging
import re
import json
from typing import Any, Callable, Dict, Optional

import async_timeout

from homeassistant import config_entries, core
from homeassistant.helpers import aiohttp_client
from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)
import voluptuous as vol

from .const import (
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
        return self._name

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
    def device_state_attributes(self) -> Dict[str, Any]:
        return self.attrs

    async def async_update(self):
        try:
            with async_timeout.timeout(30):
                query = {'email':'{self.email}', 'password':'{self.password}', 'remember_me':'true'}
                url_login = 'https://foodsharing.de/api/user/login'
                response_login = await aiohttp_client.async_get_clientsession(self.hass).get(url_login, params=query)

                if not response_login.status == 200:
                    self._available = False
                    _LOGGER.exception(f"Error '{response_login.status}' - Invalid login credentials!")
        except:
            self._available = False
            _LOGGER.exception(f"Unable to login, timeout error for '{self.latitude}'?")
        try:
            with async_timeout.timeout(30):
                url = 'https://foodsharing.de/api/baskets/nearby?lat={self.latitude}&lon={self.longitude}&distance={self.distance}'

                response = await aiohttp_client.async_get_clientsession(self.hass).get(url)
                if response.status == 200:
                    json_response = await response.json()

                    json_data = json.loads(json_response)
                
                    baskets_count = len(json_data['baskets'])

                    self.attrs[ATTR_ID] = json_data['baskets'][0]['id'],
                    self.attrs[ATTR_DESCRIPTION] = json_data['baskets'][0]['description'],
                    self.attrs[ATTR_UNTIL] = json_data['baskets'][0]['until']

                    self._state = baskets_count
                    self._available = True
                elif response.status == 401:
                    self._available = False
                    _LOGGER.exception(f"Unauthentificated! Cannot fetch data.")
                else:
                    self._available = False
                    _LOGGER.exception(f"Error '{response.status}' - Cannot retrieve data for: '{self.latitude}'")
        except:
            self._available = False
            _LOGGER.exception(f"Cannot retrieve data for: '{self.latitude}'")
                
