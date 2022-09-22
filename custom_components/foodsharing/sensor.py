"""Foodsharing.de sensor platform."""
from datetime import datetime
import logging
import re
import json
from typing import Any, Callable, Dict, Optional
from datetime import timedelta

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
    ATTR_ADDRESS,
    ATTR_MAPS_LINK,

    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=2)

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
                NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
                url = f'https://foodsharing.de/api/baskets/nearby?lat={self.latitude_fs}&lon={self.longitude_fs}&distance={self.distance}'

                response = await aiohttp_client.async_get_clientsession(self.hass).get(url)
                _LOGGER.debug(f"Fetching URL: '{url}'")
                _LOGGER.debug(f"Getting Baskets: '{response.status}' {response.text} - {response.headers}")

                #if self.gmapsapi:
                #    geolocator = GoogleV3(api_key=f"{self.gmapsapi}")
                #locator = Nominatim(user_agent="openmapquest")

                if response.status == 200:
                    raw_html = await response.text()
                    json_data = json.loads(raw_html)

                    # Doesnt work due to: TypeError: the JSON object must be str, bytes or bytearray, not dict
                    #json_response = await response.json()
                    #json_data = json.loads(json_response)

                    _LOGGER.debug(f"JSON Response: '{json_data}'")

                    baskets_count = len(json_data['baskets'])
                    baskets = []
                    if baskets_count > 0:
                        json_data['baskets'] = sorted(json_data['baskets'], key=lambda x : x['id'], reverse=True)
                        count = 0
                        for id in json_data['baskets']:
                            #Convert Time to human readable time
                            json_data['baskets'][count]['until'] = datetime.fromtimestamp(json_data['baskets'][count]['until']).strftime('%c')
                            picture = json_data['baskets'][count]['picture']

                            #Convert to human readable location address
                            location_human_readable = "unavailable"
                            maps_link = "unavailable"
                            if json_data['baskets'][count]['lat']:
                                maps_link = f"https://www.google.de/maps/place/{json_data['baskets'][count]['lat']},+{json_data['baskets'][count]['lon']}"
                                try:
                                    headers = {
                                        "user-agent": "Foodsharing Homeassistant Custom Integration",
                                    }

                                    params = (
                                        ("lat", json_data['baskets'][count]['lat']),
                                        ("lon", json_data['baskets'][count]['lon']),
                                        ("format", "geojson"),
                                    )
                                    response_nominatim = await aiohttp_client.async_get_clientsession(self.hass).get(NOMINATIM_URL, params=params, headers=headers)
                                    _LOGGER.debug(f"Nominatim Request: '{params}' '{response_nominatim.status}' {response_nominatim.text} - {response_nominatim.headers}")

                                    if response_nominatim.status == 200:
                                        raw_html_nominatim = await response_nominatim.text()
                                        json_data_nominatim = json.loads(raw_html_nominatim)
                                        location_human_readable = f"{json_data_nominatim['features'][0]['properties']['address']['road']} {json_data_nominatim['features'][0]['properties']['address']['house_number']}, {json_data_nominatim['features'][0]['properties']['address']['postcode']} {json_data_nominatim['features'][0]['properties']['address']['city']}"
                                        maps_link = f"https://www.google.de/maps/place/{json_data_nominatim['features'][0]['properties']['address']['road']}+{json_data_nominatim['features'][0]['properties']['address']['house_number']}+{json_data_nominatim['features'][0]['properties']['address']['postcode']}+{json_data_nominatim['features'][0]['properties']['address']['city']}"
                                        maps_link = maps_link.replace(" ", "+")
                                        _LOGGER.debug(f"Nominatim Answer: '{json_data_nominatim}'")
                                except Exception as ex:
                                    _LOGGER.debug(f"Error on recieving human readable address via OpenMap API for {json_data['baskets'][count]['lat']}, {json_data['baskets'][count]['lat']}.")
                                    _LOGGER.debug(f"Error {ex}.")

                            if not picture:
                                picture = "unavailable"
                            else:
                                picture = f"https://foodsharing.de/images/basket/medium-{picture}"

                            baskets.append(
                                {
                                    ATTR_ID: json_data['baskets'][count]['id'],
                                    ATTR_DESCRIPTION: json_data['baskets'][count]['description'],
                                    ATTR_ADDRESS: location_human_readable,
                                    ATTR_MAPS_LINK: maps_link,
                                    ATTR_UNTIL: json_data['baskets'][count]['until'],
                                    ATTR_PICTURE: picture
                                }
                            )
                            count += 1
                    else:
                        baskets.append(
                            {
                                ATTR_ID: "",
                                ATTR_DESCRIPTION: ""
                            }
                        )

                    self.attrs[ATTR_BASKETS] = baskets
                    self.attrs[ATTR_ATTRIBUTION] = f"last updated {datetime.now()} \n{ATTRIBUTION}"
                    self._state = baskets_count
                    self._available = True
                elif response.status == 503:
                    _LOGGER.exception(f"Error 503 - cannot reach foodsharing api. Most likely the API is under Maintainance right now.")
                    self._available = False
                elif response.status == 401:
                    #Unauthentificated -> Login first
                    try:
                        with async_timeout.timeout(30):
                            json_parameters = {'email':f'{self.email}', 'password':f'{self.password}', 'remember_me':'true'}

                            url_login = 'https://foodsharing.de/api/user/login'
                            #headers = {'Content-Type: application/json'}
                            response_login = await aiohttp_client.async_get_clientsession(self.hass).post(url_login, json=json_parameters)
                            _LOGGER.debug(f"Login: 'email':f'{self.email}' 'remember_me':'true' '{response_login.status}' {response_login.text} - {response_login.headers}")

                            if response_login.status == 200:
                                try:
                                    response = await aiohttp_client.async_get_clientsession(self.hass).get(url)
                                    _LOGGER.debug(f"Fetching URL: '{url}'")
                                    _LOGGER.debug(f"Getting Baskets: '{response.status}' {response.text} - {response.headers}")

                                    if response.status == 200:
                                        raw_html = await response.text()
                                        json_data = json.loads(raw_html)

                                        _LOGGER.debug(f"JSON Response: '{json_data}")

                                        baskets_count = len(json_data['baskets'])
                                        baskets = []
                                        if baskets_count > 0:
                                            json_data['baskets'] = sorted(json_data['baskets'], key=lambda x : x['id'], reverse=True)
                                            count = 0
                                            for id in json_data['baskets']:
                                                #Convert Time to human readable time
                                                json_data['baskets'][count]['until'] = datetime.fromtimestamp(json_data['baskets'][count]['until']).strftime('%c')
                                                picture = json_data['baskets'][count]['picture']

                                                #Convert to human readable location address
                                                location_human_readable = "unavailable"
                                                maps_link = "unavailable"
                                                if json_data['baskets'][count]['lat']:
                                                    maps_link = f"https://www.google.de/maps/place/{json_data['baskets'][count]['lat']},+{json_data['baskets'][count]['lon']}"
                                                    try:
                                                        headers = {
                                                            "user-agent": "Foodsharing Homeassistant Custom Integration",
                                                        }

                                                        params = (
                                                            ("lat", json_data['baskets'][count]['lat']),
                                                            ("lon", json_data['baskets'][count]['lon']),
                                                            ("format", "geojson"),
                                                        )
                                                        response_nominatim = await aiohttp_client.async_get_clientsession(self.hass).get(NOMINATIM_URL, params=params, headers=headers)
                                                        _LOGGER.debug(f"Nominatim Request: '{params}' '{response_nominatim.status}' {response_nominatim.text} - {response_nominatim.headers}")

                                                        if response_nominatim.status == 200:
                                                            raw_html_nominatim = await response_nominatim.text()
                                                            json_data_nominatim = json.loads(raw_html_nominatim)
                                                            location_human_readable = f"{json_data_nominatim['features'][0]['properties']['address']['road']} {json_data_nominatim['features'][0]['properties']['address']['house_number']}, {json_data_nominatim['features'][0]['properties']['address']['postcode']} {json_data_nominatim['features'][0]['properties']['address']['city']}"
                                                            maps_link = f"https://www.google.de/maps/place/{json_data_nominatim['features'][0]['properties']['address']['road']}+{json_data_nominatim['features'][0]['properties']['address']['house_number']}+{json_data_nominatim['features'][0]['properties']['address']['postcode']}+{json_data_nominatim['features'][0]['properties']['address']['city']}"
                                                            maps_link = maps_link.replace(" ", "+")
                                                            _LOGGER.debug(f"Nominatim Answer: '{json_data_nominatim}'")
                                                    except Exception as ex:
                                                        _LOGGER.debug(f"Error on recieving human readable address via OpenMap API for {json_data['baskets'][count]['lat']}, {json_data['baskets'][count]['lat']}.")
                                                        _LOGGER.debug(f"Error {ex}.")

                                                if not picture:
                                                    picture = "unavailable"
                                                else:
                                                    picture = f"https://foodsharing.de/images/basket/medium-{picture}"

                                                baskets.append(
                                                    {
                                                        ATTR_ID: json_data['baskets'][count]['id'],
                                                        ATTR_DESCRIPTION: json_data['baskets'][count]['description'],
                                                        ATTR_ADDRESS: location_human_readable,
                                                        ATTR_MAPS_LINK: maps_link,
                                                        ATTR_UNTIL: json_data['baskets'][count]['until'],
                                                        ATTR_PICTURE: picture
                                                    }
                                                )
                                                count += 1
                                        else:
                                            baskets.append(
                                                {
                                                    ATTR_ID: "",
                                                    ATTR_DESCRIPTION: ""
                                                }
                                            )

                                        self.attrs[ATTR_BASKETS] = baskets
                                        self.attrs[ATTR_ATTRIBUTION] = f"last updated {datetime.now()} \n{ATTRIBUTION}"
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
                                _LOGGER.exception(f"Error '{response_login.status}' - Invalid login credentials for {self.email} with HIDDEN! Please check your credentials.")
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
