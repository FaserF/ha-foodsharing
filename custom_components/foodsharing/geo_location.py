"""Geo-location platform for Foodsharing."""

import logging
import math
from typing import Any

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_EMAIL, CONF_LATITUDE_FS, CONF_LONGITUDE_FS, DOMAIN
from .coordinator import FoodsharingCoordinator

_LOGGER = logging.getLogger(__name__)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    r = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the geo_location platform."""
    coordinator: FoodsharingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    # Maintain a registry of active locations to map dynamic updates from the API.

    # We will use a dictionary to track active entities
    active_entities: dict[str, GeolocationEvent] = {}

    def async_update_entities() -> None:
        """Update active geo-locations."""
        if not coordinator.data:
            return

        new_entities: list[GeolocationEvent] = []
        current_ids = set()

        # Baskets
        for basket in coordinator.data.get("baskets", []):
            raw_id = basket.get("id")
            if raw_id is None:
                continue
            basket_id = f"basket_{raw_id}"
            current_ids.add(basket_id)

            if basket_id not in active_entities:
                basket_entity = FoodsharingBasketGeoLocation(coordinator, entry, basket)
                active_entities[basket_id] = basket_entity
                new_entities.append(basket_entity)

        # Fairteiler (Food Share Points)
        for i, fp in enumerate(coordinator.data.get("fairteiler", [])):
            raw_id = fp.get("id")
            fp_id = f"fp_{raw_id}" if raw_id is not None else f"fp_noid_{i}"
            current_ids.add(fp_id)

            if fp_id not in active_entities:
                fp_entity = FoodsharingFairteilerGeoLocation(coordinator, entry, fp, fp_id)
                active_entities[fp_id] = fp_entity
                new_entities.append(fp_entity)

        if new_entities:
            async_add_entities(new_entities)

        # Remove stale entities
        stale_ids = set(active_entities.keys()) - current_ids
        for stale_id in stale_ids:
            entity = active_entities.pop(stale_id)
            hass.async_create_task(entity.async_remove(force_remove=True))

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
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self.entry = entry
        self._basket_id = str(basket["id"])

        self._attr_unique_id = f"foodsharing_basket_{self._basket_id}"
        self._attr_icon = "mdi:basket"

        # Store home coordinates for distance calculation
        try:
            self._home_lat = float(entry.data.get(CONF_LATITUDE_FS, 0))
            self._home_lon = float(entry.data.get(CONF_LONGITUDE_FS, 0))
        except (ValueError, TypeError):
            self._home_lat = 0.0
            self._home_lon = 0.0

        # Initial data
        self._update_from_basket(basket)

    def _update_from_basket(self, basket: dict[str, Any]) -> None:
        """Update attributes from basket data."""
        self._attr_name = (
            f"Basket {self._basket_id}: {basket.get('available_until', '')}"
        )
        try:
            self._attr_latitude = float(basket["latitude"])
            self._attr_longitude = float(basket["longitude"])
        except (ValueError, TypeError, KeyError):
            self._attr_latitude = None  # type: ignore[assignment]
            self._attr_longitude = None  # type: ignore[assignment]

        self._attr_source = DOMAIN

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the extra state attributes."""
        data = self.coordinator.data
        if not data or not isinstance(data, dict):
            return {"keyword_match": False}

        baskets = data.get("baskets")
        if not isinstance(baskets, list):
            return {"keyword_match": False}

        basket = next(
            (
                b
                for b in baskets
                if isinstance(b, dict) and str(b.get("id")) == self._basket_id
            ),
            None,
        )
        if basket:
            return {"keyword_match": basket.get("keyword_match", False)}
        return {"keyword_match": False}

    @property
    def distance(self) -> float | None:
        """Return distance from configured search center in km."""
        if self._attr_latitude is not None and self._attr_longitude is not None:
            return round(_haversine(self._home_lat, self._home_lon, self._attr_latitude, self._attr_longitude), 1)
        return None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data and isinstance(self.coordinator.data.get("baskets"), list):
            for basket in self.coordinator.data["baskets"]:
                if isinstance(basket, dict) and str(basket.get("id")) == self._basket_id:
                    self._update_from_basket(basket)
                    self.async_write_ha_state()
                    return

        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        data = self.coordinator.data
        if not data or not isinstance(data, dict):
            return False

        baskets = data.get("baskets")
        if not isinstance(baskets, list):
            return False

        for basket in baskets:
            if isinstance(basket, dict) and str(basket.get("id")) == self._basket_id:
                return True

        return False


class FoodsharingFairteilerGeoLocation(CoordinatorEntity[FoodsharingCoordinator], GeolocationEvent):  # type: ignore[misc]
    """Represents a Foodsharing Fairteiler (Food Share Point) on the map."""

    def __init__(
        self,
        coordinator: FoodsharingCoordinator,
        entry: ConfigEntry,
        fp: dict[str, Any],
        unique_id: str,
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self.entry = entry
        self._fp_id = unique_id

        self._attr_unique_id = f"foodsharing_fairteiler_{self._fp_id}"
        self._attr_icon = "mdi:storefront"

        # Get coordinates for device mapping
        lat = self.entry.data.get(CONF_LATITUDE_FS, "")
        lon = self.entry.data.get(CONF_LONGITUDE_FS, "")
        email = self.entry.data.get(CONF_EMAIL, "")

        # Location Device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{email}_{lat}_{lon}")},
            name=f"Foodsharing Location ({lat}, {lon})",
            manufacturer="Foodsharing.de",
            model="Location Tracker",
            via_device=(DOMAIN, email),
        )

        # Store home coordinates for distance calculation
        try:
            self._home_lat = float(lat) if lat else 0.0
            self._home_lon = float(lon) if lon else 0.0
        except (ValueError, TypeError):
            self._home_lat = 0.0
            self._home_lon = 0.0

        # Initial data
        self._update_from_fp(fp)

    def _update_from_fp(self, fp: dict[str, Any]) -> None:
        """Update attributes from food share point data."""
        self._attr_name = f"Fairteiler: {fp.get('name', 'Unknown')}"
        try:
            self._attr_latitude = float(fp["latitude"])
            self._attr_longitude = float(fp["longitude"])
        except (ValueError, TypeError, KeyError):
            self._attr_latitude = None  # type: ignore[assignment]
            self._attr_longitude = None  # type: ignore[assignment]

        self._attr_source = DOMAIN

    @property
    def distance(self) -> float | None:
        """Return distance from configured search center in km."""
        if self._attr_latitude is not None and self._attr_longitude is not None:
            return round(_haversine(self._home_lat, self._home_lon, self._attr_latitude, self._attr_longitude), 1)
        return None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data and isinstance(self.coordinator.data.get("fairteiler"), list):
            for i, fp in enumerate(self.coordinator.data["fairteiler"]):
                raw_id = fp.get("id")
                fp_id = f"fp_{raw_id}" if raw_id is not None else f"fp_noid_{i}"
                if fp_id == self._fp_id:
                    self._update_from_fp(fp)
                    self.async_write_ha_state()
                    return

        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        data = self.coordinator.data
        if not data or not isinstance(data, dict):
            return False

        fairteilers = data.get("fairteiler")
        if not isinstance(fairteilers, list):
            return False

        for i, fp in enumerate(fairteilers):
            raw_id = fp.get("id")
            fp_id = f"fp_{raw_id}" if raw_id is not None else f"fp_noid_{i}"
            if fp_id == self._fp_id:
                return True

        return False
