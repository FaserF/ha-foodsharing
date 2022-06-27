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
    HomeAssistantType,
)
import voluptuous as vol

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

    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
# Time between updating data
# Unused variable??
SCAN_INTERVAL = timedelta(minutes=30)

async def async_setup_entry(
    hass: HomeAssistantType, entry: ConfigType, async_add_entities
):
    """Setup sensors from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug("Sensor async_setup_entry")
    if entry.options:
        config.update(entry.options)
    sensors = FoodsharingSensor(config, hass)
    async_add_entities(sensors, update_before_add=True)
    async_add_entities(
        [
            FoodsharingSensor(config, hass)
        ],
        update_before_add=True
    )

class FoodsharingSensor(Entity):
    """Collects and represents foodsharing baskets based on given coordinates"""

    def __init__(self, config, hass: HomeAssistantType):
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
        #return self._name
        return f"Foodsharing-{self.latitude_fs}"

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
        #_LOGGER.debug(f"HA Parameters: 'email':'{self.email}', 'password':'HIDDEN', 'lat':'{self.latitude_fs}', 'long':'{self.longitude_fs}', 'distance':'{self.distance}'")
        
        try:
            with async_timeout.timeout(30):
                url = f'https://foodsharing.de/api/baskets/nearby?lat={self.latitude_fs}&lon={self.longitude_fs}&distance={self.distance}'

                response = await aiohttp_client.async_get_clientsession(self.hass).get(url)

                _LOGGER.debug(f"Getting Baskets: '{response.status}' {response.text} - {response.headers}")
                _LOGGER.debug(f"Fetching URL: '{url}'")

                if response.status == 200:
                    raw_html = await response.text()
                    json_data = json.loads(raw_html)

                    # Doesnt work due to: TypeError: the JSON object must be str, bytes or bytearray, not dict
                    #json_response = await response.json()
                    #json_data = json.loads(json_response)

                    _LOGGER.debug(f"JSON Response: '{json_data}")
                
                    baskets_count = len(json_data['baskets'])
                    baskets = []
                    if baskets_count > 0:
                        #_LOGGER.debug(f"JSON first basket id: '{json_data['baskets'][0]['id']}'")
                        count = 0
                        for id in json_data['baskets']:
                            #Convert Time to human readable time
                            json_data['baskets'][count]['until'] = datetime.fromtimestamp(json_data['baskets'][count]['until']).strftime('%c')
                            picture = json_data['baskets'][count]['picture']
                            if not picture:
                                baskets.append(
                                    {
                                        ATTR_ID: json_data['baskets'][count]['id'],
                                        ATTR_DESCRIPTION: json_data['baskets'][count]['description'],
                                        ATTR_UNTIL: json_data['baskets'][count]['until'],
                                    }
                                )
                            else:
                                baskets.append(
                                    {
                                        ATTR_ID: json_data['baskets'][count]['id'],
                                        ATTR_DESCRIPTION: json_data['baskets'][count]['description'],
                                        ATTR_UNTIL: json_data['baskets'][count]['until'],
                                        ATTR_PICTURE: f"https://foodsharing.de/images/basket/medium-{picture}"
                                    }
                                )
                            count += 1

                    self.attrs[ATTR_BASKETS] = baskets
                    #self.attrs[ATTR_ATTRIBUTION] = f"last updated {self.updated.strftime('%d %b, %Y  %H:%M:%S')} \n{ATTRIBUTION}"
                    self.attrs[ATTR_ATTRIBUTION] = f"{ATTRIBUTION}"
                    self._state = baskets_count
                    self._available = True
                elif response.status == 401:
                    #Unauthentificated -> Login first
                    try:
                        with async_timeout.timeout(30):
                            json_parameters = {'email':f'{self.email}', 'password':f'{self.password}', 'remember_me':'true'}

                            url_login = 'https://foodsharing.de/api/user/login'
                            #headers = {'Content-Type: application/json'}
                            response_login = await aiohttp_client.async_get_clientsession(self.hass).post(url_login, json=json_parameters)
                            _LOGGER.debug(f"Login: '{json_parameters}' '{response_login.status}' {response_login.text} - {response_login.headers}")

                            if response_login.status == 200:
                                try:
                                    response = await aiohttp_client.async_get_clientsession(self.hass).get(url)

                                    _LOGGER.debug(f"Getting Baskets: '{response.status}' {response.text} - {response.headers}")
                                    _LOGGER.debug(f"Fetching URL: '{url}'")

                                    if response.status == 200:
                                        raw_html = await response.text()
                                        json_data = json.loads(raw_html)

                                        _LOGGER.debug(f"JSON Response: '{json_data}")
                                    
                                        baskets_count = len(json_data['baskets'])
                                        baskets = []
                                        if baskets_count > 0:
                                            #_LOGGER.debug(f"JSON first basket id: '{json_data['baskets'][0]['id']}'")
                                            count = 0
                                            for id in json_data['baskets']:
                                                #Convert Time to human readable time
                                                json_data['baskets'][count]['until'] = datetime.fromtimestamp(json_data['baskets'][count]['until']).strftime('%c')
                                                picture = json_data['baskets'][count]['picture']
                                                if not picture:
                                                    baskets.append(
                                                        {
                                                            ATTR_ID: json_data['baskets'][count]['id'],
                                                            ATTR_DESCRIPTION: json_data['baskets'][count]['description'],
                                                            ATTR_UNTIL: json_data['baskets'][count]['until'],
                                                        }
                                                    )
                                                else:
                                                    baskets.append(
                                                        {
                                                            ATTR_ID: json_data['baskets'][count]['id'],
                                                            ATTR_DESCRIPTION: json_data['baskets'][count]['description'],
                                                            ATTR_UNTIL: json_data['baskets'][count]['until'],
                                                            ATTR_PICTURE: f"https://foodsharing.de/images/basket/medium-{picture}"
                                                        }
                                                    )
                                                count += 1
                                        else: 
                                            baskets.append(
                                                {
                                                    ATTR_ID: ""
                                                }
                                            )
                                        self.attrs[ATTR_BASKETS] = baskets
                                        self.attrs[ATTR_ATTRIBUTION] = f"last updated {self.updated.strftime('%d %b, %Y  %H:%M:%S')} \n{ATTRIBUTION}"
                                        self._state = baskets_count
                                        self._available = True
                                    else:
                                        self._available = False
                                        _LOGGER.exception(f"Error on update after sign in: '{response.status}' - Cannot retrieve data for: '{self.latitude_fs}' '{self.longitude_fs}'")
                                except:
                                    self._available = False
                                    _LOGGER.exception(f"Cannot retrieve data for: '{self.latitude_fs}' '{self.longitude_fs}'")
                            elif response_login.status == 400:
                                _LOGGER.exception(f"Bad request. Most likely because you are already signed in and cant sign in twice. Or json credentials were missing. Continuing... - '{response_login.text}'")
                                self._available = False
                            elif response_login.status == 405:
                                _LOGGER.exception(f"Invalid request. Please report this issue to the developer. '{response_login.text}'")
                            else:
                                self._available = False
                                _LOGGER.exception(f"Error '{response_login.status}' - Invalid login credentials for {self.email} with {self.password}!")
                    except:
                        self._available = False
                        _LOGGER.exception(f"Unable to login for '{self.email}'")
                elif response.status == 405:
                    self._available = False
                    _LOGGER.exception(f"Invalid request. Please report this issue to the developer. - '{response.text}'")
                else:
                    self._available = False
                    _LOGGER.exception(f"Error '{response.status}' - Cannot retrieve data for: '{self.latitude_fs}' '{self.longitude_fs}'")
        except:
            self._available = False
            _LOGGER.exception(f"Cannot retrieve data for: '{self.latitude_fs}' '{self.longitude_fs}'")
