"""Foodsharing.de binary sensor platform."""

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import FoodsharingCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Setup binary sensors from a config entry."""
    coordinator: FoodsharingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    email = hass.data[DOMAIN][entry.entry_id]["email"]

    entities: list[BinarySensorEntity] = []

    # Create account-wide sensors only once per email
    account_key = f"account_binary_sensors_{email}"
    if account_key not in hass.data[DOMAIN]:
        hass.data[DOMAIN][account_key] = True
        entities.append(FoodsharingSleepingHatSensor(coordinator, email))

    async_add_entities(entities)


class FoodsharingSleepingHatSensor(CoordinatorEntity[FoodsharingCoordinator], BinarySensorEntity):  # type: ignore[misc]
    """Displays the user's sleeping hat status."""

    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FoodsharingCoordinator, email: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.email = email
        self._attr_has_entity_name = True
        self.translation_key = "sleeping_hat"
        self._attr_unique_id = f"Foodsharing-SleepingHat-{email}"
        self._attr_device_class = BinarySensorDeviceClass.PRESENCE  # No better fit?
        self._attr_icon = "mdi:sleep"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="foodsharing.de",
            model="Account",
        )

    @property
    def is_on(self) -> bool:
        """Return true if the user is sleeping (has the hat on)."""
        data = self.coordinator.data.get("account", {}).get("profile", {})
        return bool(data.get("isSleeping", False))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes."""
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }
