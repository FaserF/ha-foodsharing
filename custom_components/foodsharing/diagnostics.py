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
    "picture",  # Don't leak personal URLs
    "store_name",
    "fairteiler_name",
    "basket_display_name",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = entry_data.get("coordinator")

    diagnostics_data = {
        "info": async_redact_data(entry.data, TO_REDACT),
        "options": async_redact_data(entry.options, TO_REDACT),
    }

    if coordinator is not None:
        diagnostics_data["data"] = (
            async_redact_data(coordinator.data, TO_REDACT)
            if coordinator.data is not None
            else None
        )

    return diagnostics_data
