"""Diagnostics support for Foodsharing."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN

TO_REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD,
    "email",
    "password",
    "picture",  # Don't leak personal URLs
    "name",  # Redact fairteiler/store names for privacy
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    diagnostics_data = {
        "info": async_redact_data(entry.data, TO_REDACT),
        "options": async_redact_data(entry.options, TO_REDACT),
        "data": (
            async_redact_data(coordinator.data, TO_REDACT) if coordinator.data else None
        ),
    }

    return diagnostics_data
