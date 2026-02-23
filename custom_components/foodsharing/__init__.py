"""Foodsharing.de Custom Component."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_LATITUDE_FS, CONF_LONGITUDE_FS, DOMAIN
from .coordinator import FoodsharingCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.GEO_LOCATION, Platform.BUTTON, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Foodsharing from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = FoodsharingCoordinator(hass, entry)
    await coordinator.login()
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    # Register service
    async def handle_request_basket(call: Any) -> None:
        """Handle the request_basket service call."""
        basket_id = call.data.get("basket_id")
        if not basket_id:
            return
        url = f"https://foodsharing.de/api/baskets/{basket_id}/request"
        try:
            async with coordinator.session.post(url) as response:
                if response.status == 200:
                    _LOGGER.info("Successfully requested basket %s", basket_id)
                    await coordinator.async_request_refresh()
                else:
                    _LOGGER.error(
                        "Failed to request basket %s: HTTP %s", basket_id, response.status
                    )
        except Exception as err:
            _LOGGER.error("Error requesting basket %s: %s", basket_id, err)

    hass.services.async_register(DOMAIN, "request_basket", handle_request_basket)

    # Registers update listener to update config entry when options are updated.
    unsub_options_update_listener = entry.add_update_listener(options_update_listener)
    # Store a reference to the unsubscribe function to cleanup if an entry is unloaded.
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
        # Remove options_update_listener
        if "unsub_options_update_listener" in hass.data[DOMAIN][entry.entry_id]:
            hass.data[DOMAIN][entry.entry_id]["unsub_options_update_listener"]()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old configuration entries to the latest version."""
    _LOGGER.debug("Migrating config entry from version %s", config_entry.version)

    if config_entry.version in [1, 2]:
        new: dict[str, Any] = dict(config_entry.data)
        new_options: dict[str, Any] = dict(config_entry.options)

        if config_entry.version == 1:
            # Existing configs from V1 lack coordinates. Default to Home Assistant core coordinates.
            if CONF_LATITUDE_FS not in new:
                new[CONF_LATITUDE_FS] = hass.config.latitude
            if CONF_LONGITUDE_FS not in new:
                new[CONF_LONGITUDE_FS] = hass.config.longitude

            # Recalculate unique_id for Multi-Location support
            email = new.get("email", "")
            lat = new.get(CONF_LATITUDE_FS, "")
            lon = new.get(CONF_LONGITUDE_FS, "")
            new_unique_id = f"{email}_{lat}_{lon}"

        if config_entry.version == 1:
            # Apply the migration using built-in methods
            hass.config_entries.async_update_entry(
                config_entry, data=new, version=2, unique_id=new_unique_id
            )

        if "keywords" not in new_options:
            new_options["keywords"] = ""

        hass.config_entries.async_update_entry(
            config_entry, options=new_options, version=3
        )

    _LOGGER.info(
        "Successfully migrated foodsharing config entry to version %s",
        config_entry.version,
    )
    return True
