import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DISTANCE,
    CONF_DOMAIN,
    CONF_EMAIL,
    CONF_KEYWORDS,
    CONF_LATITUDE_FS,
    CONF_LOCATION,
    CONF_LOCATIONS,
    CONF_LONGITUDE_FS,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_TOTP,
    CONF_USE_BETA_API,
    DOMAIN,
)
from .helpers import mask_email

_LOGGER = logging.getLogger(__name__)


async def validate_credentials(
    hass: HomeAssistant,
    email: str,
    password: str,
    totp: str | None = None,
    use_beta: bool = False,
    domain: str = "foodsharing_de",
) -> str | bool | dict[str, Any]:
    """Validate the user credentials against the foodsharing API."""
    session = async_get_clientsession(hass)
    base_domain = "foodsharing.de"
    if domain == "foodsharing_at":
        base_domain = "foodsharing.at"
    elif domain == "foodsharing_ch":
        base_domain = "foodsharing.ch"

    base_url = f"https://beta.{base_domain}" if use_beta else f"https://{base_domain}"
    login_url = f"{base_url}/api/user/login"
    headers = {"User-Agent": "HomeAssistant-Foodsharing/1.0 (+https://github.com/FaserF/ha-foodsharing)"}
    timeout = aiohttp.ClientTimeout(total=10)

    if not totp:
        try:
            current_url = f"{base_url}/api/user/current"
            async with session.get(current_url, headers=headers, timeout=timeout) as current_resp:
                if current_resp.status == 200:
                    current_data = await current_resp.json()
                    if isinstance(current_data, dict) and "id" in current_data:
                        # Validate that the current session belongs to the requested email
                        # The API doesn't always return the email in /user/current,
                        # so if we are provided a password, we should probably just login anyway
                        # to be safe, OR we check if the ID matches what we expect if we had it.
                        # For simplicity and correctness as requested:
                        # we will skip the short-circuit if we want to be absolutely sure.
                        _LOGGER.debug(
                            "Found existing session for user %s, but proceeding with login to validate %s",
                            current_data["id"],
                            mask_email(email),
                        )
        except Exception as err:
            _LOGGER.debug("Session check failed (ignoring): %s", err)

    try:
        login_payload = {"email": email, "password": password, "rememberMe": True}
        if totp:
            login_payload["code"] = totp

        _LOGGER.debug(
            "Attempting login for %s (TOTP: %s, Beta: %s)",
            mask_email(email),
            "Yes" if totp else "No",
            use_beta,
        )
        async with session.post(
            login_url, json=login_payload, timeout=timeout, headers=headers
        ) as response:
            if response.status == 200:
                data = await response.json()
                user_id = None
                if isinstance(data, dict):
                    user_id = data.get("id") or (data.get("user") or {}).get("id")

                _LOGGER.debug(
                    "Login successful for %s, user_id: %s",
                    mask_email(email),
                    user_id,
                )
                return str(user_id) if user_id else True

            elif response.status == 400:
                try:
                    body = await response.json()
                    if isinstance(body, dict) and body.get("code") == "2fa_required":
                        _LOGGER.debug(
                            "2FA required for %s",
                            mask_email(email),
                        )
                        return {"2fa_required": True}
                    _LOGGER.warning(
                        "Login failed (400) for %s: %s",
                        mask_email(email),
                        body,
                    )
                except Exception:
                    text = await response.text()
                    _LOGGER.warning(
                        "Login failed (400) for %s with non-JSON body: %s",
                        mask_email(email),
                        text,
                    )
                return False
            else:
                body = await response.text()
                _LOGGER.warning(
                    "Login failed with status %s for %s: %s",
                    response.status,
                    mask_email(email),
                    body,
                )
                return False
    except (TimeoutError, aiohttp.ClientError) as err:
        _LOGGER.error(
            "Error validating credentials for %s (network/timeout): %s",
            mask_email(email),
            err,
        )
        return "cannot_connect"
    except Exception as err:
        _LOGGER.exception(
            "Unexpected error validating credentials for %s: %s",
            mask_email(email),
            err,
        )
        return False
    return False


def _location_to_dict(location: dict[str, Any]) -> dict[str, Any]:
    """Convert a HA LocationSelector value to our storage format."""
    lat = location.get("latitude", 0)
    lon = location.get("longitude", 0)
    radius_meters = location.get("radius", 7000)
    dist = round(radius_meters / 1000.0, 1)
    return {"latitude": lat, "longitude": lon, "distance": dist}


class FoodsharingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg, misc]
    """Handle a config flow for Foodsharing."""

    VERSION = 5

    def __init__(self) -> None:
        """Initialize config flow."""
        self._user_input: dict[str, Any] = {}
        self._locations: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step: credentials + first location."""
        errors = {}

        if user_input is not None:
            try:
                email = user_input[CONF_EMAIL]
                password = user_input[CONF_PASSWORD]
                use_beta = user_input.get(CONF_USE_BETA_API, False)
                domain = user_input.get(CONF_DOMAIN, "foodsharing_de")

                res = await validate_credentials(
                    self.hass, email, password, use_beta=use_beta, domain=domain
                )
                if res == "cannot_connect":
                    errors["base"] = "cannot_connect"
                elif isinstance(res, dict) and res.get("2fa_required"):
                    self._user_input = user_input
                    return await self.async_step_totp()
                elif not res:
                    errors["base"] = "invalid_auth"
                else:
                    self._user_input = dict(user_input)
                    if CONF_LOCATION in user_input:
                        self._locations = [_location_to_dict(user_input[CONF_LOCATION])]
                    return await self.async_step_add_location()
            except Exception as err:
                _LOGGER.exception("Unexpected error in async_step_user: %s", err)
                errors["base"] = "unknown"

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
                        "radius": 7000,
                    },
                ): selector.LocationSelector(
                    selector.LocationSelectorConfig(radius=True)
                ),
                vol.Optional(CONF_KEYWORDS, default=""): str,
                vol.Required(CONF_SCAN_INTERVAL, default=2): cv.positive_int,
                vol.Required(CONF_DOMAIN, default="foodsharing_de"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="foodsharing_de", label="foodsharing.de"),
                            selector.SelectOptionDict(value="foodsharing_at", label="foodsharing.at"),
                            selector.SelectOptionDict(value="foodsharing_ch", label="foodsharing.ch"),
                        ],
                        translation_key="domain",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_USE_BETA_API, default=False): bool,
            },
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle re-authentication."""
        self._user_input = dict(entry_data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm re-authentication."""
        errors = {}
        if user_input is not None:
            email = self._user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            use_beta = self._user_input.get(CONF_USE_BETA_API, False)

            res = await validate_credentials(self.hass, email, password, use_beta=use_beta)
            if res == "cannot_connect":
                errors["base"] = "cannot_connect"
            elif isinstance(res, dict) and res.get("2fa_required"):
                self._user_input[CONF_PASSWORD] = password
                return await self.async_step_totp()
            elif not res:
                errors["base"] = "invalid_auth"
            else:
                new_data = {**self._user_input, CONF_PASSWORD: password}
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data=new_data
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            description_placeholders={CONF_EMAIL: self._user_input[CONF_EMAIL]},
            errors=errors,
        )

    async def async_step_totp(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle 2FA (TOTP) step."""
        errors = {}
        if user_input is not None:
            try:
                code = user_input["code"]
                res = await validate_credentials(
                    self.hass,
                    self._user_input[CONF_EMAIL],
                    self._user_input[CONF_PASSWORD],
                    code,
                    self._user_input.get(CONF_USE_BETA_API, False)
                )
                if res == "cannot_connect":
                    errors["base"] = "cannot_connect"
                elif not res or (isinstance(res, dict) and res.get("2fa_required")):
                    errors["base"] = "invalid_totp"
                else:
                    if self.context.get("source") == config_entries.SOURCE_REAUTH:
                        entry = self._get_reauth_entry()
                        new_data = {**self._user_input}
                        new_data.pop(CONF_TOTP, None)
                        return self.async_update_reload_and_abort(entry, data=new_data)

                    if CONF_LOCATION in self._user_input:
                        self._locations = [_location_to_dict(self._user_input[CONF_LOCATION])]
                    return await self.async_step_add_location()
            except Exception as err:
                _LOGGER.exception("Unexpected error in async_step_totp: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="totp",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
        )

    async def async_step_add_location(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask whether to add another location."""
        if user_input is not None:
            if user_input.get("add_another"):
                return await self.async_step_extra_location()
            return await self._async_finish_setup()

        return self.async_show_form(
            step_id="add_location",
            data_schema=vol.Schema(
                {
                    vol.Required("add_another", default=False): bool,
                }
            ),
        )

    async def async_step_extra_location(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Show a location picker for an additional location."""
        if user_input is not None:
            if CONF_LOCATION in user_input:
                self._locations.append(_location_to_dict(user_input[CONF_LOCATION]))
            return await self.async_step_add_location()

        return self.async_show_form(
            step_id="extra_location",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LOCATION,
                        default={
                            "latitude": self.hass.config.latitude,
                            "longitude": self.hass.config.longitude,
                            "radius": 7000,
                        },
                    ): selector.LocationSelector(
                        selector.LocationSelectorConfig(radius=True)
                    ),
                }
            ),
        )

    async def _async_finish_setup(self) -> config_entries.ConfigFlowResult:
        """Finish the setup flow after validation."""
        try:
            user_input = dict(self._user_input)
            email = user_input[CONF_EMAIL]

            user_input.pop(CONF_LOCATION, None)

            if self._locations:
                primary = self._locations[0]
                user_input[CONF_LATITUDE_FS] = primary["latitude"]
                user_input[CONF_LONGITUDE_FS] = primary["longitude"]
                user_input[CONF_DISTANCE] = primary["distance"]

            user_input[CONF_LOCATIONS] = self._locations
            user_input.pop(CONF_TOTP, None)

            unique_id = email.lower()
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            _LOGGER.debug(
                "Initialized new foodsharing entry for: %s",
                mask_email(email),
            )
            return self.async_create_entry(title=email, data=user_input)
        except Exception as err:
            _LOGGER.exception("Unexpected error in _async_finish_setup: %s", err)
            raise

    @staticmethod
    @callback  # type: ignore[untyped-decorator]
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):  # type: ignore[misc]
    """Handle an options flow"""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._locations: list[dict[str, Any]] = []
        self._user_input: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle options flow — credentials + primary location."""
        errors = {}
        if user_input is not None:
            new_email = user_input[CONF_EMAIL]
            new_password = user_input[CONF_PASSWORD]
            new_use_beta = user_input.get(CONF_USE_BETA_API, False)
            new_domain = user_input.get(CONF_DOMAIN, "foodsharing_de")

            options = {**self.config_entry.data, **self.config_entry.options}
            old_email = options.get(CONF_EMAIL)
            old_password = options.get(CONF_PASSWORD)
            old_use_beta = options.get(CONF_USE_BETA_API, False)
            old_domain = options.get(CONF_DOMAIN, "foodsharing_de")

            if (
                new_email != old_email
                or new_password != old_password
                or new_use_beta != old_use_beta
                or new_domain != old_domain
            ):
                is_valid = await validate_credentials(
                    self.hass, new_email, new_password, use_beta=new_use_beta, domain=new_domain
                )
                if is_valid == "cannot_connect":
                    errors["base"] = "cannot_connect"
                elif isinstance(is_valid, dict) and is_valid.get("2fa_required"):
                    errors["base"] = "2fa_required"
                    # We don't have a dedicated TOTP step for options yet,
                    # but we should at least block and show the error.
                    # Actually the prompt says "invoke the 2FA handling flow ... or set errors['base']='2fa_required'"
                elif not is_valid:
                    errors["base"] = "invalid_auth"

            if not errors:
                self._user_input = dict(user_input)
                if CONF_LOCATION in user_input:
                    new_primary = _location_to_dict(user_input[CONF_LOCATION])
                    # Merge primary location into existing options state
                    options = {**self.config_entry.data, **self.config_entry.options}
                    existing_locs: list[dict[str, Any]] = list(
                        options.get(CONF_LOCATIONS, [])
                    )
                    if existing_locs:
                        existing_locs[0] = new_primary
                    else:
                        existing_locs = [new_primary]
                    self._locations = existing_locs
                return await self.async_step_manage_locations()

        options = {**self.config_entry.data, **self.config_entry.options}

        existing_locations: list[dict] = options.get(CONF_LOCATIONS, [])
        primary = existing_locations[0] if existing_locations else {}

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
                        "latitude": primary.get("latitude", options.get(CONF_LATITUDE_FS, self.hass.config.latitude)),
                        "longitude": primary.get("longitude", options.get(CONF_LONGITUDE_FS, self.hass.config.longitude)),
                        "radius": primary.get("distance", options.get(CONF_DISTANCE, 7)) * 1000,
                    },
                ): selector.LocationSelector(
                    selector.LocationSelectorConfig(radius=True)
                ),
                vol.Optional(
                    CONF_KEYWORDS, default=options.get(CONF_KEYWORDS, "")
                ): str,
                vol.Required(
                    CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, 2)
                ): cv.positive_int,
                vol.Required(
                    CONF_DOMAIN, default=options.get(CONF_DOMAIN, "foodsharing_de")
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="foodsharing_de", label="foodsharing.de"),
                            selector.SelectOptionDict(value="foodsharing_at", label="foodsharing.at"),
                            selector.SelectOptionDict(value="foodsharing_ch", label="foodsharing.ch"),
                        ],
                        translation_key="domain",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_USE_BETA_API, default=options.get(CONF_USE_BETA_API, False)
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )

    async def async_step_manage_locations(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask whether to add another location or finish."""
        if user_input is not None:
            if user_input.get("add_another"):
                return await self.async_step_extra_location_option()
            return self._finish_options()

        return self.async_show_form(
            step_id="manage_locations",
            description_placeholders={
                "count": str(len(self._locations)),
            },
            data_schema=vol.Schema(
                {
                    vol.Required("add_another", default=False): bool,
                }
            ),
        )

    async def async_step_extra_location_option(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Show a location picker for an additional location in options."""
        if user_input is not None:
            if CONF_LOCATION in user_input:
                self._locations.append(_location_to_dict(user_input[CONF_LOCATION]))
            return await self.async_step_manage_locations()

        return self.async_show_form(
            step_id="extra_location_option",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LOCATION,
                        default={
                            "latitude": self.hass.config.latitude,
                            "longitude": self.hass.config.longitude,
                            "radius": 7000,
                        },
                    ): selector.LocationSelector(
                        selector.LocationSelectorConfig(radius=True)
                    ),
                }
            ),
        )

    def _finish_options(self) -> config_entries.ConfigFlowResult:
        """Finalize the options entry."""
        user_input = dict(self._user_input)
        user_input.pop(CONF_LOCATION, None)

        if self._locations:
            primary = self._locations[0]
            user_input[CONF_LATITUDE_FS] = primary["latitude"]
            user_input[CONF_LONGITUDE_FS] = primary["longitude"]
            user_input[CONF_DISTANCE] = primary["distance"]

        user_input[CONF_LOCATIONS] = self._locations

        # Check if email changed and update config entry data/unique_id
        current_email = self.config_entry.data.get(CONF_EMAIL)
        new_email = user_input.get(CONF_EMAIL)

        if new_email and new_email != current_email:
            new_unique_id = new_email.lower()
            # Check for unique_id collisions
            existing_entry = next(
                (
                    e
                    for e in self.hass.config_entries.async_entries(DOMAIN)
                    if e.unique_id == new_unique_id and e.entry_id != self.config_entry.entry_id
                ),
                None,
            )
            if existing_entry:
                _LOGGER.error(
                    "Cannot change email to %s: another entry already exists for this account",
                    mask_email(new_email),
                )
                # We return an abort here because we can't update unique_id to a duplicate
                return self.async_abort(reason="already_configured")

            _LOGGER.debug(
                "Email changed from %s to %s, updating config entry",
                mask_email(current_email),
                mask_email(new_email),
            )
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, **user_input},
                unique_id=new_unique_id,
            )
            # We return an empty entry because we updated the main entry directly
            return self.async_create_entry(title="", data={})

        return self.async_create_entry(title="", data=user_input)
