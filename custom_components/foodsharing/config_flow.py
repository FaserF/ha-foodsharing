import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_LATITUDE_FS,
    CONF_LONGITUDE_FS,
    CONF_DISTANCE,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow"""

    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_LATITUDE_FS])
            self._abort_if_unique_id_configured()
            _LOGGER.debug("Initialized new foodsharing sensor with id: {unique_id}")
            return self.async_create_entry(title=user_input[CONF_LATITUDE_FS], data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_LATITUDE_FS, default=self.hass.config.latitude): cv.string,
                vol.Required(CONF_LONGITUDE_FS, default=self.hass.config.longitude): cv.string,
                vol.Required(CONF_DISTANCE, default=7): cv.positive_int,
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_SCAN_INTERVAL, default=2): cv.positive_int,
            },
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow"""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        errors = {}
        if user_input is not None:
            validate_options(user_input, errors)
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema({
            vol.Optional(CONF_DISTANCE, default=self.config_entry.options.get(CONF_DISTANCE, 7)): cv.positive_int,
            vol.Optional(CONF_SCAN_INTERVAL, default=self.config_entry.options.get(CONF_SCAN_INTERVAL, 2)): cv.positive_int,
            vol.Optional(CONF_EMAIL, default=self.config_entry.options.get(CONF_EMAIL, "")): str,
            vol.Optional(CONF_PASSWORD, default=self.config_entry.options.get(CONF_PASSWORD, "")): str,
        })

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )


def validate_options(user_input, errors):
    """Validate the options in the OptionsFlow."""
    for key in [CONF_DISTANCE, CONF_SCAN_INTERVAL, CONF_EMAIL, CONF_PASSWORD]:
        value = user_input.get(key)
        if key in [CONF_DISTANCE, CONF_SCAN_INTERVAL]:
            try:
                if value is not None:
                    vol.PositiveInt()(value)
            except vol.Invalid:
                _LOGGER.exception("Configuration option %s=%s is incorrect", key, value)
                errors["base"] = "option_error"
        elif key in [CONF_EMAIL, CONF_PASSWORD]:
            if not isinstance(value, str) or not value.strip():
                errors[key] = "invalid_format"
