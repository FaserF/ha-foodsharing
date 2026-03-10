"""Helper utilities for the Foodsharing integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

from .const import CONF_DISTANCE, CONF_LATITUDE_FS, CONF_LOCATIONS, CONF_LONGITUDE_FS


def get_locations_from_entry(entry: ConfigEntry) -> list[dict]:
    """Return the list of search locations for a config entry.

    Supports both the new ``locations`` list format (v5+) and the legacy
    flat ``latitude`` / ``longitude`` / ``distance`` keys (v3/v4).
    """
    locations = entry.options.get(CONF_LOCATIONS, entry.data.get(CONF_LOCATIONS))
    if locations:
        return list(locations)

    lat = entry.options.get(CONF_LATITUDE_FS, entry.data.get(CONF_LATITUDE_FS))
    lon = entry.options.get(CONF_LONGITUDE_FS, entry.data.get(CONF_LONGITUDE_FS))
    dist = entry.options.get(CONF_DISTANCE, entry.data.get(CONF_DISTANCE, 7))
    if lat is not None and lon is not None:
        return [{"latitude": lat, "longitude": lon, "distance": dist}]
    return []


def parse_extra_locations(text: str) -> list[dict[str, float]]:
    """Parse extra locations from a semicolon-separated string of lat,lon,dist."""
    locations: list[dict[str, float]] = []
    if not text:
        return locations

    for part in text.split(";"):
        try:
            coords = [p.strip() for p in part.split(",") if p.strip()]
            if len(coords) < 2:
                continue
            lat = float(coords[0])
            lon = float(coords[1])
            dist = float(coords[2]) if len(coords) > 2 else 7.0
            locations.append({"latitude": lat, "longitude": lon, "distance": dist})
        except (ValueError, IndexError):
            continue
    return locations
