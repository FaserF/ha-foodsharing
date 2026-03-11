"""Helpers for Foodsharing integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import CONF_LOCATIONS

_LOGGER = logging.getLogger(__name__)


def get_locations_from_entry(entry: ConfigEntry) -> list[dict[str, Any]]:
    """Extract and prioritize locations from config entry."""
    locations: list[dict[str, Any]] = []

    # 1. First, check if there's a list of locations in the entry options/data
    locs_data = entry.options.get(CONF_LOCATIONS, entry.data.get(CONF_LOCATIONS, []))
    if isinstance(locs_data, list) and locs_data:
        for loc in locs_data:
            if isinstance(loc, dict) and "latitude" in loc and "longitude" in loc:
                locations.append(loc)
        if locations:
            return locations

    # 2. Legacy: check the main latitude/longitude/distance fields
    # (These might still be there from older versions)
    data = entry.options.copy()
    data.update(entry.data)

    try:
        lat = float(data.get("latitude", 0))
        lon = float(data.get("longitude", 0))
        dist = float(data.get("distance", 7.0))
        if lat != 0 and lon != 0:
            locations.append({"latitude": lat, "longitude": lon, "distance": dist})
    except (ValueError, TypeError):
        pass

    # 3. Last resort: check if there's a location string we can parse
    # Format: "latitude,longitude,distance"
    loc_str = data.get("location", "")
    if isinstance(loc_str, str) and loc_str:
        try:
            coords = loc_str.split(",")
            lat = float(coords[0])
            lon = float(coords[1])
            dist = float(coords[2]) if len(coords) > 2 else 7.0
            locations.append({"latitude": lat, "longitude": lon, "distance": dist})
        except (ValueError, IndexError):
            pass
    return locations


def mask_email(email: str | None) -> str:
    """Mask email address for logging (e.g., u***@example.com)."""
    if not isinstance(email, str) or "@" not in email:
        return "***"
    e_str = str(email)
    at_pos = e_str.find("@")
    if at_pos < 0:
        return "***"
    first = e_str[:1]
    domain = e_str[at_pos + 1 :]
    return f"{first}***@{domain}"
