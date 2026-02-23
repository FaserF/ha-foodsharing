"""Foodsharing.de Custom Component."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import FoodsharingCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.GEO_LOCATION, Platform.BUTTON, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Foodsharing from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = FoodsharingCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

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
            if "latitude_fs" not in new:
                new["latitude_fs"] = hass.config.latitude
            if "longitude_fs" not in new:
                new["longitude_fs"] = hass.config.longitude

            # Recalculate unique_id for Multi-Location support
            email = new.get("email", "")
            lat = new.get("latitude_fs", "")
            lon = new.get("longitude_fs", "")
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
