"""Foodsharing.de sensor platform."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_BASKETS,
    ATTRIBUTION,
    CONF_LATITUDE_FS,
    CONF_LONGITUDE_FS,
    DOMAIN,
)
from .coordinator import FoodsharingCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Setup sensors from a config entry created in the integrations UI."""
    coordinator: FoodsharingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    baskets_sensor = FoodsharingSensor(coordinator, entry)
    messages_sensor = FoodsharingMessagesSensor(coordinator, entry)
    bells_sensor = FoodsharingBellsSensor(coordinator, entry)

    async_add_entities(
        [baskets_sensor, messages_sensor, bells_sensor], update_before_add=True
    )


class FoodsharingSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Collects and represents foodsharing baskets based on given coordinates."""

    def __init__(self, coordinator: FoodsharingCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry

        # We try to get from data, fallback to options
        data = entry.options if entry.options else entry.data

        self.latitude_fs = data.get(
            CONF_LATITUDE_FS,
            (
                coordinator.hass.config.latitude
                if hasattr(coordinator.hass, "config")
                else ""
            ),
        )
        self.longitude_fs = data.get(
            CONF_LONGITUDE_FS,
            (
                coordinator.hass.config.longitude
                if hasattr(coordinator.hass, "config")
                else ""
            ),
        )

        self._attr_name = f"Foodsharing Baskets {self.latitude_fs}"
        self._attr_unique_id = f"Foodsharing-Baskets-{entry.entry_id}"
        self._attr_icon = "mdi:basket-unfill"
        self._attr_unit_of_measurement = "baskets"

        # Location Device
        self._attr_device_info = {
            "identifiers": {
                (
                    DOMAIN,
                    f"{entry.data.get('email', '')}_{self.latitude_fs}_{self.longitude_fs}",
                )
            },
            "name": f"Foodsharing Location ({self.latitude_fs}, {self.longitude_fs})",
            "manufacturer": "Foodsharing.de",
            "model": "Location Tracker",
            "via_device": (DOMAIN, entry.data.get("email", "")),
        }

    @property
    def state(self) -> int | None:
        """Return the state of the entity (number of baskets)."""
        if self.coordinator.data is not None and "baskets" in self.coordinator.data:
            return len(self.coordinator.data["baskets"])
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {
            CONF_LATITUDE_FS: self.latitude_fs,
            CONF_LONGITUDE_FS: self.longitude_fs,
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

        if self.coordinator.data is not None and "baskets" in self.coordinator.data:
            attrs[ATTR_BASKETS] = self.coordinator.data["baskets"]

        return attrs


class FoodsharingMessagesSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Represents unread messages on Foodsharing."""

    def __init__(self, coordinator: FoodsharingCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_name = "Foodsharing Unread Messages"
        self._attr_unique_id = f"Foodsharing-Messages-{entry.entry_id}"
        self._attr_icon = "mdi:message"
        self._attr_unit_of_measurement = "messages"

        # Account Device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data.get("email", ""))},
            "name": f"Foodsharing Account ({entry.data.get('email', '')})",
            "manufacturer": "Foodsharing.de",
            "model": "Account",
        }

    @property
    def state(self) -> int | None:
        if self.coordinator.data:
            return int(self.coordinator.data.get("messages", 0))
        return 0


class FoodsharingBellsSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Represents unread bell notifications on Foodsharing."""

    def __init__(self, coordinator: FoodsharingCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_name = "Foodsharing Notifications"
        self._attr_unique_id = f"Foodsharing-Bells-{entry.entry_id}"
        self._attr_icon = "mdi:bell"
        self._attr_unit_of_measurement = "notifications"

        # Account Device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data.get("email", ""))},
            "name": f"Foodsharing Account ({entry.data.get('email', '')})",
            "manufacturer": "Foodsharing.de",
            "model": "Account",
        }

    @property
    def state(self) -> int | None:
        if self.coordinator.data:
            return int(self.coordinator.data.get("bells", 0))
        return 0
