"""Foodsharing.de sensor platform."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTRIBUTION,
    CONF_LATITUDE_FS,
    CONF_LONGITUDE_FS,
    DOMAIN,
)
from .coordinator import FoodsharingCoordinator
from .helpers import get_locations_from_entry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Setup sensors from a config entry created in the integrations UI."""
    coordinator: FoodsharingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    email = hass.data[DOMAIN][entry.entry_id]["email"]

    locations = get_locations_from_entry(entry)
    entities: list[SensorEntity] = []

    for idx, loc in enumerate(locations):
        entities.append(
            FoodsharingSensor(
                coordinator,
                entry,
                loc_idx=idx,
                lat=loc["latitude"],
                lon=loc["longitude"],
            )
        )

    # Create account-wide sensors only once per email (even across multiple entries)
    account_key = f"account_sensors_{email}"
    if account_key not in hass.data[DOMAIN]:
        hass.data[DOMAIN][account_key] = True
        entities.append(FoodsharingMessagesSensor(coordinator, email))
        entities.append(FoodsharingBellsSensor(coordinator, email))
        entities.append(FoodsharingPickupsSensor(coordinator, email))

    async_add_entities(entities)


class FoodsharingSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Collects and represents foodsharing baskets based on given coordinates."""

    def __init__(
        self,
        coordinator: FoodsharingCoordinator,
        entry: ConfigEntry,
        loc_idx: int,
        lat: float,
        lon: float,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self.entry_id = entry.entry_id
        self.loc_idx = loc_idx
        self.latitude_fs = lat
        self.longitude_fs = lon

        self._attr_has_entity_name = True
        self._attr_name = "Baskets"
        self._attr_unique_id = f"Foodsharing-Baskets-{entry.entry_id}-{loc_idx}"
        self._attr_icon = "mdi:basket-unfill"
        self._attr_native_unit_of_measurement = "baskets"

        email = coordinator.email
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{email}_{lat}_{lon}")},
            name=f"Foodsharing Location ({lat}, {lon})",
            manufacturer="Foodsharing.de",
            model="Location Tracker",
            via_device=(DOMAIN, email),
        )

    def _get_loc_data(self) -> dict[str, Any]:
        """Return coordinator location data for this sensor's location slot."""
        if self.coordinator.data:
            entry_locs: list[dict[str, Any]] = (
                self.coordinator.data.get("locations", {}).get(self.entry_id, [])
            )
            if self.loc_idx < len(entry_locs):
                return entry_locs[self.loc_idx]
        return {}

    @property
    def native_value(self) -> int:
        """Return the number of baskets."""
        return len(self._get_loc_data().get("baskets", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        loc_data = self._get_loc_data()
        baskets = loc_data.get("baskets", [])
        return {
            CONF_LATITUDE_FS: self.latitude_fs,
            CONF_LONGITUDE_FS: self.longitude_fs,
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "basket_count": len(baskets),
            "baskets": baskets,
        }


class FoodsharingMessagesSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Represents unread messages on Foodsharing."""

    def __init__(self, coordinator: FoodsharingCoordinator, email: str) -> None:
        super().__init__(coordinator)
        self.email = email
        self._attr_has_entity_name = True
        self._attr_name = "Unread Messages"
        self._attr_unique_id = f"Foodsharing-Messages-{email}"
        self._attr_icon = "mdi:message"
        self._attr_native_unit_of_measurement = "messages"

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
        if self.coordinator.data:
            return int(self.coordinator.data.get("account", {}).get("messages", 0))
        return 0


class FoodsharingBellsSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Represents unread bell notifications on Foodsharing."""

    def __init__(self, coordinator: FoodsharingCoordinator, email: str) -> None:
        super().__init__(coordinator)
        self.email = email
        self._attr_has_entity_name = True
        self._attr_name = "Notifications"
        self._attr_unique_id = f"Foodsharing-Bells-{email}"
        self._attr_icon = "mdi:bell"
        self._attr_native_unit_of_measurement = "notifications"

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
        if self.coordinator.data:
            return int(self.coordinator.data.get("account", {}).get("bells", 0))
        return 0


class FoodsharingPickupsSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Represents upcoming pickups on Foodsharing."""

    def __init__(self, coordinator: FoodsharingCoordinator, email: str) -> None:
        super().__init__(coordinator)
        self.email = email
        self._attr_has_entity_name = True
        self._attr_name = "Upcoming Pickups"
        self._attr_unique_id = f"Foodsharing-Pickups-{email}"
        self._attr_icon = "mdi:calendar-clock"
        self._attr_native_unit_of_measurement = "pickups"

        # Account Device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="Foodsharing.de",
            model="Account",
        )

    @property
    def native_value(self) -> int:
        """Return the number of upcoming pickups."""
        if self.coordinator.data:
            pickups = self.coordinator.data.get("account", {}).get("pickups", [])
            return len(pickups) if isinstance(pickups, list) else 0
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for pickups."""
        if self.coordinator.data:
            pickups = self.coordinator.data.get("account", {}).get("pickups", [])
            return {"pickups": pickups}
        return {}
