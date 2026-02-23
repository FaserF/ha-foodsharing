"""Geo-location platform for Foodsharing."""

import logging
from typing import Any

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FoodsharingCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the geo_location platform."""
    coordinator: FoodsharingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    # Maintain a registry of active locations to map dynamic updates from the API.

    # We will use a dictionary to track active entities
    active_entities: dict[str, Any] = {}

    def async_update_entities() -> None:
        """Update active geo-locations."""
        if not coordinator.data:
            return

        new_entities = []
        current_ids = set()

        # Baskets
        for basket in coordinator.data.get("baskets", []):
            basket_id = f"basket_{basket['id']}"
            current_ids.add(basket_id)

            if basket_id not in active_entities:
                entity = FoodsharingBasketGeoLocation(coordinator, entry, basket)
                active_entities[basket_id] = entity
                new_entities.append(entity)

        # Fairteiler (Food Share Points)
        for fp in coordinator.data.get("fairteiler", []):
            fp_id = f"fp_{fp['id']}"
            current_ids.add(fp_id)

            if fp_id not in active_entities:
                entity = FoodsharingFairteilerGeoLocation(coordinator, entry, fp)
                active_entities[fp_id] = entity
                new_entities.append(entity)

        if new_entities:
            async_add_entities(new_entities)

        # We also need to remove entities that are no longer available.
        # CoordinatorEntity doesn't dynamically remove themselves, but available=False will handle that.

    # Register listener
    coordinator.async_add_listener(async_update_entities)

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

            # Simple distance calculation if available, GeolocationEvent allows source
            self._attr_source = DOMAIN
        except ValueError, TypeError, KeyError:
            self._attr_latitude = None  # type: ignore[assignment]
            self._attr_longitude = None  # type: ignore[assignment]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the extra state attributes."""
        basket = next(
            (
                b
                for b in self.coordinator.data.get("baskets", [])
                if str(b["id"]) == self._basket_id
            ),
            None,
        )
        if basket:
            return {"keyword_match": basket.get("keyword_match", False)}
        return {"keyword_match": False}

    @property
    def distance(self) -> float | None:
        """Return distance to center. (HA core calculates if lat/lon are set)"""
        return None  # Let HomeAssistant calculate it using the zone

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data and "baskets" in self.coordinator.data:
            for basket in self.coordinator.data["baskets"]:
                if str(basket["id"]) == self._basket_id:
                    self._update_from_basket(basket)
                    self.async_write_ha_state()
                    return

        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        if self.coordinator.data is None or "baskets" not in self.coordinator.data:
            return False

        for basket in self.coordinator.data["baskets"]:
            if str(basket["id"]) == self._basket_id:
                return True

        return False


class FoodsharingFairteilerGeoLocation(CoordinatorEntity[FoodsharingCoordinator], GeolocationEvent):  # type: ignore[misc]
    """Represents a Foodsharing Fairteiler (Food Share Point) on the map."""

    def __init__(
        self,
        coordinator: FoodsharingCoordinator,
        entry: ConfigEntry,
        fp: dict[str, Any],
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self.entry = entry
        self._fp_id = str(fp["id"])

        self._attr_unique_id = f"foodsharing_fairteiler_{self._fp_id}"
        self._attr_icon = "mdi:storefront"

        # Initial data
        self._update_from_fp(fp)

    def _update_from_fp(self, fp: dict[str, Any]) -> None:
        """Update attributes from food share point data."""
        self._attr_name = f"Fairteiler: {fp.get('name', 'Unknown')}"
        try:
            self._attr_latitude = float(fp["latitude"])
            self._attr_longitude = float(fp["longitude"])
            self._attr_source = DOMAIN
        except ValueError, TypeError, KeyError:
            self._attr_latitude = None  # type: ignore[assignment]
            self._attr_longitude = None  # type: ignore[assignment]

        # Get coordinates for device mapping
        lat = self.entry.data.get("latitude_fs", "")
        lon = self.entry.data.get("longitude_fs", "")
        email = self.entry.data.get("email", "")

        # Location Device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{email}_{lat}_{lon}")},
            "name": f"Foodsharing Location ({lat}, {lon})",
            "manufacturer": "Foodsharing.de",
            "model": "Location Tracker",
            "via_device": (DOMAIN, email),
        }

    @property
    def distance(self) -> float | None:
        """Return distance to center."""
        return None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data and "fairteiler" in self.coordinator.data:
            for fp in self.coordinator.data["fairteiler"]:
                if str(fp["id"]) == self._fp_id:
                    self._update_from_fp(fp)
                    self.async_write_ha_state()
                    return

        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        if self.coordinator.data is None or "fairteiler" not in self.coordinator.data:
            return False

        for fp in self.coordinator.data["fairteiler"]:
            if str(fp["id"]) == self._fp_id:
                return True

        return False
