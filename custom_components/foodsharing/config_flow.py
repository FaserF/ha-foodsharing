import logging
from typing import Any

import aiohttp
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DISTANCE,
    CONF_EMAIL,
    CONF_KEYWORDS,
    CONF_LATITUDE_FS,
    CONF_LOCATION,
    CONF_LONGITUDE_FS,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def validate_credentials(
    hass: HomeAssistant, email: str, password: str
) -> str | bool:
    """Validate the user credentials against the foodsharing.de API."""
    session = async_get_clientsession(hass)
    login_url = "https://foodsharing.de/api/user/login"
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        login_payload = {"email": email, "password": password, "rememberMe": True}
        async with session.post(
            login_url, json=login_payload, timeout=timeout
        ) as response:
            if response.status == 200:
                data = await response.json()
                if "id" in data:
                    return str(data["id"])
                return True
            else:
                return False
        return False
    except (TimeoutError, aiohttp.ClientError) as err:
        _LOGGER.error("Error validating credentials (network/timeout): %s", err)
        return "cannot_connect"
    except Exception as err:
        _LOGGER.error("Unexpected error validating credentials: %s", err)
        return False


class FoodsharingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg, misc]
    """Handle a config flow for Foodsharing."""

    VERSION = 3

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            # Validate credentials
            user_id = await validate_credentials(self.hass, email, password)
            if user_id == "cannot_connect":
                errors["base"] = "cannot_connect"
            elif not user_id:
                errors["base"] = "invalid_auth"
            else:
                # Expand unique ID to include location so one email can have multiple locations
                # We round to 4 decimals to allow minor fuzzing but distinct areas
                lat = None
                lon = None
                if CONF_LOCATION in user_input:
                    location = user_input[CONF_LOCATION]
                    lat = round(location.get("latitude", 0), 4)
                    lon = round(location.get("longitude", 0), 4)
                    unique_id = f"{email}_{lat}_{lon}"
                else:
                    unique_id = (
                        str(user_id)
                        if (isinstance(user_id, (int, str)) and not isinstance(user_id, bool))
                        else email
                    )

                await self.async_set_unique_id(unique_id.lower())
                self._abort_if_unique_id_configured()

                # Transform Location Selector output into simple latitude and longitude
                if CONF_LOCATION in user_input:
                    location = user_input.pop(CONF_LOCATION)
                    user_input[CONF_LATITUDE_FS] = location.get("latitude", 0)
                    user_input[CONF_LONGITUDE_FS] = location.get("longitude", 0)
                    # Radius from map selector always wins
                    radius_meters = location.get("radius", 7000)
                    user_input[CONF_DISTANCE] = round(radius_meters / 1000)
                    # Update local lat/lon for title
                    lat = round(user_input[CONF_LATITUDE_FS], 4)
                    lon = round(user_input[CONF_LONGITUDE_FS], 4)

                _LOGGER.debug(
                    "Initialized new foodsharing sensor with id: %s", unique_id
                )
                title = f"{email}"
                if lat is not None and lon is not None:
                    title = f"{email} ({lat}, {lon})"

                return self.async_create_entry(title=title, data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_LOCATION,
                    default={
                        "latitude": self.hass.config.latitude,
                        "longitude": self.hass.config.longitude,
                        "radius": 7000,  # 7km default
                    },
                ): selector.LocationSelector(
                    selector.LocationSelectorConfig(radius=True)
                ),
                vol.Required(CONF_DISTANCE, default=7): cv.positive_int,
                vol.Optional(CONF_KEYWORDS, default=""): str,
                vol.Required(CONF_SCAN_INTERVAL, default=2): cv.positive_int,
            },
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback  # type: ignore[untyped-decorator]
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):  # type: ignore[misc]
    """Handle an options flow"""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle options flow."""
        errors = {}
        if user_input is not None:
            # Check if credentials changed
            new_email = user_input[CONF_EMAIL]
            new_password = user_input[CONF_PASSWORD]
            old_email = self.config_entry.data.get(CONF_EMAIL)
            old_password = self.config_entry.data.get(CONF_PASSWORD)

            if new_email != old_email or new_password != old_password:
                is_valid = await validate_credentials(
                    self.hass, new_email, new_password
                )
                if is_valid == "cannot_connect":
                    errors["base"] = "cannot_connect"
                elif not is_valid:
                    errors["base"] = "invalid_auth"

            if not errors:
                if CONF_LOCATION in user_input:
                    location = user_input.pop(CONF_LOCATION)
                    user_input[CONF_LATITUDE_FS] = location.get("latitude", 0)
                    user_input[CONF_LONGITUDE_FS] = location.get("longitude", 0)
                    # Radius from map selector always wins
                    radius_meters = location.get("radius", 7000)
                    user_input[CONF_DISTANCE] = round(radius_meters / 1000)

                return self.async_create_entry(title="", data=user_input)

        # Use self.config_entry.data to get the current values
        options = self.config_entry.options or self.config_entry.data

        options_schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL, default=options.get(CONF_EMAIL, "")): str,
                vol.Required(
                    CONF_PASSWORD, default=options.get(CONF_PASSWORD, "")
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_LOCATION,
                    default={
                        "latitude": options.get(
                            CONF_LATITUDE_FS, self.hass.config.latitude
                        ),
                        "longitude": options.get(
                            CONF_LONGITUDE_FS, self.hass.config.longitude
                        ),
                        "radius": options.get(CONF_DISTANCE, 7) * 1000,
                    },
                ): selector.LocationSelector(
                    selector.LocationSelectorConfig(radius=True)
                ),
                vol.Required(
                    CONF_DISTANCE, default=options.get(CONF_DISTANCE, 7)
                ): cv.positive_int,
                vol.Optional(
                    CONF_KEYWORDS, default=options.get(CONF_KEYWORDS, "")
                ): str,
                vol.Required(
                    CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, 2)
                ): cv.positive_int,
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )
