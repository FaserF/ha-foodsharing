"""Button platform for Foodsharing."""

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
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
    """Set up the button platform."""
    coordinator: FoodsharingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    active_baskets: dict[str, ButtonEntity] = {}

    def async_update_entities() -> None:
        """Update active buttons."""
        if not coordinator.data:
            return

        new_entities: list[ButtonEntity] = []

        # Baskets to Request
        for basket in coordinator.data.get("baskets", []):
            basket_id = str(basket["id"])
            key = f"near_{basket_id}"

            if key not in active_baskets:
                req_entity = FoodsharingRequestButton(coordinator, entry, basket)
                active_baskets[key] = req_entity
                new_entities.append(req_entity)

        # Own Baskets to Close
        for own in coordinator.data.get("own_baskets", []):
            own_id = str(own["id"])
            key = f"own_{own_id}"
            if key not in active_baskets:
                close_entity = FoodsharingCloseOwnBasketButton(coordinator, entry, own)
                active_baskets[key] = close_entity
                new_entities.append(close_entity)

        if new_entities:
            async_add_entities(new_entities)

    # Register listener
    coordinator.async_add_listener(async_update_entities)

    # Initial load
    async_update_entities()


class FoodsharingRequestButton(CoordinatorEntity[FoodsharingCoordinator], ButtonEntity):  # type: ignore[misc]
    """A button to request a foodsharing basket."""

    def __init__(
        self,
        coordinator: FoodsharingCoordinator,
        entry: ConfigEntry,
        basket: dict[str, Any],
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entry = entry
        self._basket_id = str(basket["id"])

        self._attr_unique_id = f"foodsharing_request_basket_{self._basket_id}"
        self._attr_name = f"Request: {basket.get('description', 'Unknown Basket')}"
        self._attr_icon = "mdi:cart-plus"

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

    async def async_press(self) -> None:
        """Handle the button press to request a basket."""
        _LOGGER.info("Button pressed to request basket %s", self._basket_id)

        # Execute the REST call via the coordinator's authenticated session
        url = f"https://foodsharing.de/api/baskets/{self._basket_id}/request"
        try:
            # Execute POST request to request the basket
            async with self.coordinator.session.post(url) as response:
                if response.status == 200:
                    _LOGGER.info("Successfully requested basket %s", self._basket_id)
                    # Refresh data immediately
                    await self.coordinator.async_request_refresh()
                else:
                    _LOGGER.error(
                        "Failed to request basket %s. Status: %s",
                        self._basket_id,
                        response.status,
                    )
        except Exception as e:
            _LOGGER.error("Exception requesting basket: %s", e)

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


class FoodsharingCloseOwnBasketButton(CoordinatorEntity[FoodsharingCoordinator], ButtonEntity):  # type: ignore[misc]
    """A button to close a user's own active foodsharing basket."""

    def __init__(
        self,
        coordinator: FoodsharingCoordinator,
        entry: ConfigEntry,
        basket: dict[str, Any],
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entry = entry
        self._basket_id = str(basket["id"])

        self._attr_unique_id = f"foodsharing_close_basket_{self._basket_id}"
        self._attr_name = (
            f"Close Own Basket: {basket.get('description', 'Unknown Basket')}"
        )
        self._attr_icon = "mdi:cart-off"

        lat = self.entry.data.get("latitude_fs", "")
        lon = self.entry.data.get("longitude_fs", "")
        email = self.entry.data.get("email", "")

        # Use same device grouping
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{email}_{lat}_{lon}")},
            "name": f"Foodsharing Location ({lat}, {lon})",
            "manufacturer": "Foodsharing.de",
            "model": "Location Tracker",
            "via_device": (DOMAIN, email),
        }

    async def async_press(self) -> None:
        """Handle the button press to close the basket."""
        _LOGGER.info("Button pressed to close own basket %s", self._basket_id)

        url = f"https://foodsharing.de/api/baskets/{self._basket_id}/close"
        try:
            async with self.coordinator.session.post(url) as response:
                if response.status == 200:
                    _LOGGER.info("Successfully closed own basket %s", self._basket_id)
                    await self.coordinator.async_request_refresh()
                else:
                    _LOGGER.error(
                        "Failed to close own basket %s. Status: %s",
                        self._basket_id,
                        response.status,
                    )
        except Exception as e:
            _LOGGER.error("Exception closing own basket: %s", e)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        if self.coordinator.data is None or "own_baskets" not in self.coordinator.data:
            return False

        for basket in self.coordinator.data["own_baskets"]:
            if str(basket["id"]) == self._basket_id:
                return True

        return False
