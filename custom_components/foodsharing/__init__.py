"""Foodsharing.de Custom Component."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_DISTANCE,
    CONF_EMAIL,
    CONF_LATITUDE_FS,
    CONF_LOCATIONS,
    CONF_LONGITUDE_FS,
    CONF_PASSWORD,
    DOMAIN,
)
from .coordinator import FoodsharingCoordinator
from .helpers import mask_email

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.GEO_LOCATION, Platform.BUTTON, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Foodsharing from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("accounts", {})

    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]

    is_new_coordinator = email not in hass.data[DOMAIN]["accounts"]
    if is_new_coordinator:
        coordinator = FoodsharingCoordinator(hass, email, password)
        await coordinator.async_load_session()
        hass.data[DOMAIN]["accounts"][email] = coordinator
    else:
        coordinator = hass.data[DOMAIN]["accounts"][email]
        # Always update credentials to ensure they are current
        coordinator.password = password

    coordinator.add_entry(entry)

    # Initial data fetch. We use a standard refresh to avoid overly strict state checks
    try:
        await coordinator.async_refresh()
        # Ensure fresh cookies (e.g. from a successful re-auth config flow) are written to disk
        await coordinator.async_save_session()
    except Exception as ex:
        _LOGGER.warning("Initial fetch failed for %s: %s", mask_email(email), ex)

    if is_new_coordinator:
        device_registry = dr.async_get(hass)
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="Foodsharing",
            model="Account",
        )

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "email": email,
    }

    if not hass.services.has_service(DOMAIN, "request_basket"):

        async def handle_request_basket(call: Any) -> None:
            """Handle the request_basket service call."""
            basket_id = call.data.get("basket_id")
            target_email = call.data.get("email")

            if not basket_id:
                _LOGGER.error("Service request_basket called without basket_id")
                return

            accounts = hass.data[DOMAIN]["accounts"]
            if not accounts:
                _LOGGER.error("No Foodsharing accounts configured")
                return

            if target_email:
                if target_email not in accounts:
                    _LOGGER.error(
                        "Foodsharing account %s not found",
                        mask_email(target_email),
                    )
                    return
                coordinator = accounts[target_email]
            else:
                if len(accounts) > 1:
                    first_email = next(iter(accounts))
                    _LOGGER.warning(
                        "Multiple Foodsharing accounts found, using the first one (%s). "
                        "Specify 'email' in service call to target a specific account.",
                        mask_email(first_email),
                    )
                coordinator = next(iter(accounts.values()))

            url = f"{coordinator.base_url}/api/baskets/{basket_id}/request"
            try:
                async with coordinator.session.post(
                    url, headers=coordinator.authenticated_headers
                ) as response:
                    if response.status == 200:
                        _LOGGER.info(
                            "Successfully requested basket %s using account %s",
                            basket_id,
                            mask_email(coordinator.email),
                        )
                        await coordinator.async_request_refresh()
                    else:
                        _LOGGER.error(
                            "Failed to request basket %s: HTTP %s",
                            basket_id,
                            response.status,
                        )
            except Exception as err:
                _LOGGER.error("Error requesting basket %s: %s", basket_id, err)

        hass.services.async_register(DOMAIN, "request_basket", handle_request_basket)

    if not hass.services.has_service(DOMAIN, "close_basket"):

        async def handle_close_basket(call: Any) -> None:
            """Handle the close_basket service call for own baskets."""
            basket_id = call.data.get("basket_id")
            email = call.data.get("email")

            if not basket_id:
                _LOGGER.error("Service close_basket called without basket_id")
                return

            accounts = hass.data[DOMAIN]["accounts"]
            if not accounts:
                _LOGGER.error("No Foodsharing accounts configured")
                return

            if email:
                if email not in accounts:
                    _LOGGER.error(
                        "Foodsharing account %s not found",
                        mask_email(email),
                    )
                    return
                coordinator = accounts[email]
            else:
                if len(accounts) > 1:
                    first_email = next(iter(accounts))
                    _LOGGER.warning(
                        "Multiple Foodsharing accounts found, using the first one (%s). "
                        "Specify 'email' in service call to target a specific account.",
                        mask_email(first_email),
                    )
                coordinator = next(iter(accounts.values()))

            url = f"{coordinator.base_url}/api/baskets/{basket_id}/close"
            try:
                async with coordinator.session.post(
                    url, headers=coordinator.authenticated_headers
                ) as response:
                    if response.status == 200:
                        _LOGGER.info(
                            "Successfully closed own basket %s using account %s",
                            basket_id,
                            mask_email(coordinator.email),
                        )
                        await coordinator.async_request_refresh()
                    else:
                        _LOGGER.error(
                            "Failed to close own basket %s: HTTP %s",
                            basket_id,
                            response.status,
                        )
            except Exception as err:
                _LOGGER.error("Error closing own basket %s: %s", basket_id, err)

        hass.services.async_register(DOMAIN, "close_basket", handle_close_basket)

    # Registers update listener to update config entry when options are updated.
    unsub_options_update_listener = entry.add_update_listener(options_update_listener)
    hass.data[DOMAIN][entry.entry_id][
        "unsub_options_update_listener"
    ] = unsub_options_update_listener

    # Forward the setup to the specific platforms.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def options_update_listener(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok: bool = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)
        email = entry_data["email"]
        coordinator = entry_data["coordinator"]

        # Unsubscribe listener
        if "unsub_options_update_listener" in entry_data:
            entry_data["unsub_options_update_listener"]()

        # Remove entry from coordinator
        coordinator.remove_entry(entry.entry_id)

        # If no more entries for this account, remove coordinator and sentinels
        if not coordinator.entries:
            hass.data[DOMAIN]["accounts"].pop(email)
            hass.data[DOMAIN].pop(f"account_sensors_{email}", None)
            hass.data[DOMAIN].pop(f"calendars_{email}", None)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old configuration entries to the latest version."""
    _LOGGER.debug("Migrating config entry from version %s", config_entry.version)

    if config_entry.version in [1, 2]:
        new: dict[str, Any] = dict(config_entry.data)
        new_options: dict[str, Any] = dict(config_entry.options)

        if config_entry.version == 1:
            if CONF_LATITUDE_FS not in new:
                new[CONF_LATITUDE_FS] = hass.config.latitude
            if CONF_LONGITUDE_FS not in new:
                new[CONF_LONGITUDE_FS] = hass.config.longitude

            email = new.get("email", "")
            lat = new.get(CONF_LATITUDE_FS, "")
            lon = new.get(CONF_LONGITUDE_FS, "")
            new_unique_id = f"{email}_{lat}_{lon}"

            # Apply migration to version 2
            hass.config_entries.async_update_entry(
                config_entry, data=new, version=2, unique_id=new_unique_id
            )

        if "keywords" not in new_options:
            new_options["keywords"] = ""

        hass.config_entries.async_update_entry(
            config_entry, options=new_options, version=3
        )

    if config_entry.version in [3, 4]:
        new = dict(config_entry.data)
        new_options = dict(config_entry.options)

        # Migrate flat lat/lon/distance keys → locations list
        lat = new_options.get(CONF_LATITUDE_FS, new.get(CONF_LATITUDE_FS))
        lon = new_options.get(CONF_LONGITUDE_FS, new.get(CONF_LONGITUDE_FS))
        dist = new_options.get(CONF_DISTANCE, new.get(CONF_DISTANCE, 7))
        if lat is not None and lon is not None and CONF_LOCATIONS not in new:
            new[CONF_LOCATIONS] = [
                {"latitude": lat, "longitude": lon, "distance": dist}
            ]

        # Remove obsolete flat keys
        for key in (CONF_LATITUDE_FS, CONF_LONGITUDE_FS, CONF_DISTANCE):
            new.pop(key, None)
            new_options.pop(key, None)

        # Normalise unique_id to just the email address
        email = new.get(CONF_EMAIL, "").lower()

        hass.config_entries.async_update_entry(
            config_entry, data=new, options=new_options, version=5, unique_id=email
        )

    _LOGGER.info(
        "Successfully migrated foodsharing config entry to version %s",
        config_entry.version,
    )
    return True
