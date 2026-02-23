"""Foodsharing.de sensor platform."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
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

    async_add_entities([baskets_sensor, messages_sensor, bells_sensor])


class FoodsharingSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Collects and represents foodsharing baskets based on given coordinates."""

    def __init__(self, coordinator: FoodsharingCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry

        self.latitude_fs = entry.data.get(CONF_LATITUDE_FS)
        if self.latitude_fs is None:
            self.latitude_fs = (
                coordinator.hass.config.latitude
                if hasattr(coordinator.hass, "config")
                else ""
            )
        self.longitude_fs = entry.data.get(CONF_LONGITUDE_FS)
        if self.longitude_fs is None:
            self.longitude_fs = (
                coordinator.hass.config.longitude
                if hasattr(coordinator.hass, "config")
                else ""
            )

        self._attr_name = f"Foodsharing Baskets {self.latitude_fs}, {self.longitude_fs}"
        self._attr_unique_id = f"Foodsharing-Baskets-{entry.entry_id}"
        self._attr_icon = "mdi:basket-unfill"
        self._attr_native_unit_of_measurement = "baskets"

        email = entry.data.get("email", "")
        # Location Device
        self._attr_device_info = DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    f"{email}_{self.latitude_fs}_{self.longitude_fs}",
                )
            },
            name=f"Foodsharing Location ({self.latitude_fs}, {self.longitude_fs})",
            manufacturer="Foodsharing.de",
            model="Location Tracker",
            via_device=(DOMAIN, email),
        )

    @property
    def native_value(self) -> int:
        """Return the number of baskets."""
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
            attrs["basket_count"] = len(self.coordinator.data["baskets"])

        return attrs


class FoodsharingMessagesSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Represents unread messages on Foodsharing."""

    def __init__(self, coordinator: FoodsharingCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_name = "Foodsharing Unread Messages"
        self._attr_unique_id = f"Foodsharing-Messages-{entry.entry_id}"
        self._attr_icon = "mdi:message"
        self._attr_native_unit_of_measurement = "messages"

        email = entry.data.get("email", "")
        # Account Device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="Foodsharing.de",
            model="Account",
        )

    @property
    def native_value(self) -> int:
        """Return the number of unread messages."""
        if self.coordinator.data is not None:
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
        self._attr_native_unit_of_measurement = "notifications"

        email = entry.data.get("email", "")
        # Account Device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="Foodsharing.de",
            model="Account",
        )

    @property
    def native_value(self) -> int:
        """Return the number of unread bell notifications."""
        if self.coordinator.data is not None:
            return int(self.coordinator.data.get("bells", 0))
        return 0
