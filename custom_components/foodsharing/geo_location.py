"""Geo-location platform for Foodsharing."""

import logging
import math
from typing import Any

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FoodsharingCoordinator
from .helpers import get_locations_from_entry

_LOGGER = logging.getLogger(__name__)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    r = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the geo_location platform."""
    coordinator: FoodsharingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    # Track active entities by (loc_idx, entity_id) composite key
    active_entities: dict[str, GeolocationEvent] = {}

    @callback
    def async_update_entities() -> None:
        """Update active geo-locations for all locations in this entry."""
        if not coordinator.data:
            return

        locations = get_locations_from_entry(entry)
        entry_locs: list[dict[str, Any]] = coordinator.data.get("locations", {}).get(
            entry.entry_id, []
        )

        new_entities: list[GeolocationEvent] = []
        current_ids: set[str] = set()

        for idx, loc in enumerate(locations):
            if idx >= len(entry_locs):
                continue
            loc_data = entry_locs[idx]
            home_lat = loc["latitude"]
            home_lon = loc["longitude"]
            email = coordinator.email

            # Baskets
            for basket in loc_data.get("baskets", []):
                raw_id = basket.get("id")
                basket_lat = basket.get("latitude")
                basket_lon = basket.get("longitude")
                if raw_id is None or basket_lat is None or basket_lon is None:
                    continue
                basket_key = f"{idx}_basket_{raw_id}"
                current_ids.add(basket_key)

                if basket_key not in active_entities:
                    basket_entity = FoodsharingBasketGeoLocation(
                        coordinator, entry, basket, idx, home_lat, home_lon, email
                    )
                    active_entities[basket_key] = basket_entity
                    new_entities.append(basket_entity)

            # Fairteiler (Food Share Points)
            for i, fp in enumerate(loc_data.get("fairteiler", [])):
                raw_id = fp.get("id")
                fp_lat = fp.get("latitude")
                fp_lon = fp.get("longitude")
                if fp_lat is None or fp_lon is None:
                    continue
                fp_unique = f"fp_{raw_id}" if raw_id is not None else f"fp_noid_{i}"
                fp_key = f"{idx}_{fp_unique}"
                current_ids.add(fp_key)

                if fp_key not in active_entities:
                    fp_entity = FoodsharingFairteilerGeoLocation(
                        coordinator,
                        entry,
                        fp,
                        idx,
                        fp_unique,
                        home_lat,
                        home_lon,
                        email,
                    )
                    active_entities[fp_key] = fp_entity
                    new_entities.append(fp_entity)

        if new_entities:
            async_add_entities(new_entities)

        # Remove stale entities only if we actually have data for this entry
        # This prevents accidental deletion during startup race conditions
        if entry.entry_id not in coordinator.data.get("locations", {}):
            return

        stale_ids = set(active_entities.keys()) - current_ids
        if stale_ids:
            registry = er.async_get(hass)
            for stale_key in stale_ids:
                entity = active_entities.pop(stale_key)
                hass.async_create_task(entity.async_remove())

                # Also remove from registry so it doesn't show up as 'restored'
                if entity.unique_id:
                    entity_id = registry.async_get_entity_id(
                        "geo_location", DOMAIN, entity.unique_id
                    )
                    if entity_id:
                        registry.async_remove(entity_id)

    # Register listener
    unsub = coordinator.async_add_listener(async_update_entities)
    entry.async_on_unload(unsub)

    # Initial load
    async_update_entities()


class FoodsharingBasketGeoLocation(CoordinatorEntity[FoodsharingCoordinator], GeolocationEvent):  # type: ignore[misc]
    """Represents a Foodsharing Basket on the map."""

    def __init__(
        self,
        coordinator: FoodsharingCoordinator,
        entry: ConfigEntry,
        basket: dict[str, Any],
        loc_idx: int,
        home_lat: float,
        home_lon: float,
        email: str,
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self.entry = entry
        self._basket_id = str(basket["id"])
        self._loc_idx = loc_idx
        self._home_lat = home_lat
        self._home_lon = home_lon

        self._attr_unique_id = f"foodsharing_basket_{entry.entry_id}_{self._basket_id}"
        self._attr_icon = "mdi:basket"
        self._attr_source = DOMAIN

        # Location Device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{email}_{home_lat}_{home_lon}")},
            name=f"Foodsharing Location ({home_lat}, {home_lon})",
            manufacturer="foodsharing.de",
            model="Location Tracker",
            via_device=(DOMAIN, email),
        )

        self._update_from_basket(basket)

    def _update_from_basket(self, basket: dict[str, Any]) -> None:
        """Update attributes from basket data."""
        self._attr_name = f"Basket {self._basket_id}"
        try:
            self._attr_latitude = float(basket["latitude"])
            self._attr_longitude = float(basket["longitude"])
        except ValueError, TypeError, KeyError:
            self._attr_latitude = None  # type: ignore[assignment]
            self._attr_longitude = None  # type: ignore[assignment]

        self._attr_source = DOMAIN

    def _get_current_basket(self) -> dict[str, Any] | None:
        """Return current basket dict from coordinator data."""
        if not self.coordinator.data:
            return None
        entry_locs: list[dict] = self.coordinator.data.get("locations", {}).get(
            self.entry.entry_id, []
        )
        if self._loc_idx >= len(entry_locs):
            return None
        for basket in entry_locs[self._loc_idx].get("baskets", []):
            if isinstance(basket, dict) and str(basket.get("id")) == self._basket_id:
                return basket
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the extra state attributes."""
        basket = self._get_current_basket()
        return {
            "keyword_match": basket.get("keyword_match", False) if basket else False
        }

    @property
    def distance(self) -> float | None:
        """Return distance from configured search center in km."""
        if self._attr_latitude is not None and self._attr_longitude is not None:
            return round(
                _haversine(
                    self._home_lat,
                    self._home_lon,
                    self._attr_latitude,
                    self._attr_longitude,
                ),
                1,
            )
        return None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        basket = self._get_current_basket()
        if basket:
            self._update_from_basket(basket)
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return self._get_current_basket() is not None


class FoodsharingFairteilerGeoLocation(CoordinatorEntity[FoodsharingCoordinator], GeolocationEvent):  # type: ignore[misc]
    """Represents a Foodsharing Fairteiler (Food Share Point) on the map."""

    def __init__(
        self,
        coordinator: FoodsharingCoordinator,
        entry: ConfigEntry,
        fp: dict[str, Any],
        loc_idx: int,
        unique_id: str,
        home_lat: float,
        home_lon: float,
        email: str,
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self.entry = entry
        self._fp_id = unique_id
        self._loc_idx = loc_idx
        self._home_lat = home_lat
        self._home_lon = home_lon

        self._attr_unique_id = (
            f"foodsharing_{entry.entry_id}_fairteiler_{loc_idx}_{unique_id}"
        )
        self._attr_icon = "mdi:storefront"
        self._attr_source = DOMAIN

        # Location Device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{email}_{home_lat}_{home_lon}")},
            name=f"Foodsharing Location ({home_lat}, {home_lon})",
            manufacturer="foodsharing.de",
            model="Location Tracker",
            via_device=(DOMAIN, email),
        )

        self._update_from_fp(fp)

    def _update_from_fp(self, fp: dict[str, Any]) -> None:
        """Update attributes from food share point data."""
        self._attr_name = f"Fairteiler: {fp.get('name', 'Unknown')}"
        try:
            self._attr_latitude = float(fp["latitude"])
            self._attr_longitude = float(fp["longitude"])
        except ValueError, TypeError, KeyError:
            self._attr_latitude = None  # type: ignore[assignment]
            self._attr_longitude = None  # type: ignore[assignment]

        self._attr_source = DOMAIN
        self._fp_data = fp

    def _get_current_fp(self) -> dict[str, Any] | None:
        """Return current fairteiler dict from coordinator data."""
        if not self.coordinator.data:
            return None
        entry_locs: list[dict] = self.coordinator.data.get("locations", {}).get(
            self.entry.entry_id, []
        )
        if self._loc_idx >= len(entry_locs):
            return None
        for i, fp in enumerate(entry_locs[self._loc_idx].get("fairteiler", [])):
            raw_id = fp.get("id")
            fp_id = f"fp_{raw_id}" if raw_id is not None else f"fp_noid_{i}"
            if fp_id == self._fp_id and isinstance(fp, dict):
                return fp
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the extra state attributes."""
        attrs = {
            "description": self._fp_data.get("description"),
            "address": self._fp_data.get("address"),
            "picture": self._fp_data.get("picture"),
        }

        latest_post = self._fp_data.get("latest_post")
        if latest_post:
            attrs["latest_post"] = latest_post.get("body")
            attrs["latest_post_time"] = latest_post.get("time")
            attrs["latest_post_user"] = latest_post.get("user_name")

        return attrs

    @property
    def distance(self) -> float | None:
        """Return distance from configured search center in km."""
        if self._attr_latitude is not None and self._attr_longitude is not None:
            return round(
                _haversine(
                    self._home_lat,
                    self._home_lon,
                    self._attr_latitude,
                    self._attr_longitude,
                ),
                1,
            )
        return None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        fp = self._get_current_fp()
        if fp:
            self._update_from_fp(fp)
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return self._get_current_fp() is not None
