"""Foodsharing.de sensor platform."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
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

    # Device and Entity Registry Cleanup
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    # 1. Cleanup specific legacy devices (consolidated/moved)
    for old_id in ["global_stats", f"account_{email}"]:
        old_device = device_reg.async_get_device(identifiers={(DOMAIN, old_id)})
        if old_device:
            _LOGGER.debug("Removing legacy device: %s", old_id)
            device_reg.async_remove_device(old_device.id)

    # 2. Cleanup orphaned location devices
    locations = get_locations_from_entry(entry)
    current_loc_idents = {
        f"{email}_{loc['latitude']}_{loc['longitude']}" for loc in locations
    }
    devices = dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    for device in devices:
        for ident in device.identifiers:
            if (
                ident[0] == DOMAIN
                and ident[1].startswith(f"{email}_")
                and ident[1] not in current_loc_idents
            ):
                _LOGGER.debug("Removing orphaned location device: %s", ident[1])
                device_reg.async_remove_device(device.id)
                break

    # 3. Cleanup orphaned entities (old indexes or old unique_ids)
    current_prefixes = [
        f"Foodsharing-Baskets-{entry.entry_id}-{idx}" for idx in range(len(locations))
    ] + [
        f"Foodsharing-Fairteiler-{entry.entry_id}-{idx}"
        for idx in range(len(locations))
    ]
    old_orphans = ["foodsharing_global_statistics"]

    reg_entities = er.async_entries_for_config_entry(entity_reg, entry.entry_id)
    for entity in reg_entities:
        if entity.unique_id in old_orphans:
            entity_reg.async_remove(entity.entity_id)
            continue
        if (
            entity.unique_id.startswith(f"Foodsharing-Baskets-{entry.entry_id}-")
            or entity.unique_id.startswith(f"Foodsharing-Fairteiler-{entry.entry_id}-")
        ) and entity.unique_id not in current_prefixes:
            _LOGGER.debug("Removing orphaned entity: %s", entity.unique_id)
            entity_reg.async_remove(entity.entity_id)

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
        entities.append(
            FoodsharingFairteilerSensor(
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
        entities.append(FoodsharingGlobalStatsSensor(coordinator, email))
        entities.append(FoodsharingUserStatsSensor(coordinator, email))
        entities.append(FoodsharingBuddiesSensor(coordinator, email))
        entities.append(FoodsharingBananasSensor(coordinator, email))
        entities.append(FoodsharingRegionStatsSensor(coordinator, email))

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
        self.translation_key = "baskets"
        self._attr_unique_id = f"Foodsharing-Baskets-{entry.entry_id}-{loc_idx}"
        self._attr_icon = "mdi:basket-unfill"
        self._attr_native_unit_of_measurement = "baskets"

        email = coordinator.email
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{email}_{lat}_{lon}")},
            name=f"Foodsharing Location ({lat}, {lon})",
            manufacturer="foodsharing.de",
            model="Location Tracker",
            via_device=(DOMAIN, email),
        )

    def _get_loc_data(self) -> dict[str, Any]:
        """Return coordinator location data for this sensor's location slot."""
        if self.coordinator.data:
            entry_locs: list[dict[str, Any]] = self.coordinator.data.get(
                "locations", {}
            ).get(self.entry_id, [])
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
        fairteiler = loc_data.get("fairteiler", [])
        return {
            CONF_LATITUDE_FS: self.latitude_fs,
            CONF_LONGITUDE_FS: self.longitude_fs,
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "basket_count": len(baskets),
            "baskets": baskets,
            "fairteiler_count": len(fairteiler),
            "fairteiler": fairteiler,
        }


class FoodsharingFairteilerSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Represents public Fairteiler in a location."""

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
        self.translation_key = "fairteiler"
        self._attr_unique_id = f"Foodsharing-Fairteiler-{entry.entry_id}-{loc_idx}"
        self._attr_icon = "mdi:storefront"
        self._attr_native_unit_of_measurement = "fairteiler"

        email = coordinator.email
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{email}_{lat}_{lon}")},
            name=f"Foodsharing Location ({lat}, {lon})",
            manufacturer="foodsharing.de",
            model="Location Tracker",
            via_device=(DOMAIN, email),
        )

    def _get_loc_data(self) -> dict[str, Any]:
        """Return coordinator location data for this sensor's location slot."""
        if self.coordinator.data:
            entry_locs: list[dict[str, Any]] = self.coordinator.data.get(
                "locations", {}
            ).get(self.entry_id, [])
            if self.loc_idx < len(entry_locs):
                return entry_locs[self.loc_idx]
        return {}

    @property
    def native_value(self) -> int:
        """Return the number of Fairteiler."""
        return len(self._get_loc_data().get("fairteiler", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        loc_data = self._get_loc_data()
        fairteiler = loc_data.get("fairteiler", [])
        return {
            CONF_LATITUDE_FS: self.latitude_fs,
            CONF_LONGITUDE_FS: self.longitude_fs,
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "fairteiler_count": len(fairteiler),
            "fairteiler": fairteiler,
        }


class FoodsharingMessagesSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Represents unread messages on Foodsharing."""

    def __init__(self, coordinator: FoodsharingCoordinator, email: str) -> None:
        super().__init__(coordinator)
        self.email = email
        self._attr_has_entity_name = True
        self.translation_key = "unread_messages"
        self._attr_unique_id = f"Foodsharing-Messages-{email}"
        self._attr_icon = "mdi:message"
        self._attr_native_unit_of_measurement = "messages"

        # Account Device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="foodsharing.de",
            model="Account",
        )

    @property
    def native_value(self) -> int:
        """Return the number of unread messages."""
        if self.coordinator.data:
            val = self.coordinator.data.get("account", {}).get("messages", 0)
            return int(val)
        return 0


class FoodsharingBellsSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Represents unread bell notifications on Foodsharing."""

    def __init__(self, coordinator: FoodsharingCoordinator, email: str) -> None:
        super().__init__(coordinator)
        self.email = email
        self._attr_has_entity_name = True
        self.translation_key = "notifications"
        self._attr_unique_id = f"Foodsharing-Bells-{email}"
        self._attr_icon = "mdi:bell"
        self._attr_native_unit_of_measurement = "notifications"

        # Account Device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="foodsharing.de",
            model="Account",
        )

    @property
    def native_value(self) -> int:
        """Return the number of unread bell notifications."""
        if self.coordinator.data:
            val = self.coordinator.data.get("account", {}).get("bells", 0)
            return int(val)
        return 0


class FoodsharingPickupsSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Represents upcoming pickups on Foodsharing."""

    def __init__(self, coordinator: FoodsharingCoordinator, email: str) -> None:
        super().__init__(coordinator)
        self.email = email
        self._attr_has_entity_name = True
        self.translation_key = "upcoming_pickups"
        self._attr_unique_id = f"Foodsharing-Pickups-{email}"
        self._attr_icon = "mdi:calendar-clock"
        self._attr_native_unit_of_measurement = "pickups"

        # Account Device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="foodsharing.de",
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


class FoodsharingGlobalStatsSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Represents global Foodsharing.de statistics."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "kg"
    _attr_device_class = None
    _attr_state_class = "total"
    _attr_icon = "mdi:earth"
    _attr_translation_key = "global_stats"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FoodsharingCoordinator, email: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.email = email
        self._attr_unique_id = f"foodsharing_global_statistics_{email}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="foodsharing.de",
            model="Account",
        )

    @property
    def native_value(self) -> float:
        """Return the total weight saved globally (in kg)."""
        stats = self.coordinator.data.get("account", {}).get("global_stats", {})
        return float(stats.get("fetchWeight", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        stats = self.coordinator.data.get("account", {}).get("global_stats", {})
        return {
            "rescue_missions": stats.get("fetchCount"),
            "foodsavers": stats.get("countAllFoodsaver"),
            "cooperating_companies": stats.get("cooperationsCount"),
            "active_fairteiler": stats.get("countActiveFoodSharePoints"),
            "total_baskets": stats.get("totalBaskets"),
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }


class FoodsharingUserStatsSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Represents user-specific Foodsharing statistics."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "pickups"
    _attr_state_class = "total"
    _attr_icon = "mdi:account-star"
    _attr_translation_key = "user_stats"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FoodsharingCoordinator, email: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.email = email
        self._attr_unique_id = f"foodsharing_user_stats_{email}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="foodsharing.de",
            model="Account",
        )

    @property
    def native_value(self) -> int:
        """Return the number of rescues by the user."""
        stats = self.coordinator.data.get("account", {}).get("user_stats", {})
        return int(stats.get("pickup_count", stats.get("fetchCount", 0)))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        stats = self.coordinator.data.get("account", {}).get("user_stats", {})
        return {
            "weight_saved_kg": stats.get("weight_saved", stats.get("fetchWeight")),
            "rating": stats.get("rating"),
            "member_since": stats.get("member_since"),
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }


class FoodsharingBuddiesSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Displays the number of buddies."""

    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FoodsharingCoordinator, email: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.email = email
        self._attr_has_entity_name = True
        self.translation_key = "buddies"
        self._unique_id_base = f"Foodsharing-Buddies-{email}"
        self._attr_unique_id = self._unique_id_base
        self._attr_icon = "mdi:account-group"
        self._attr_native_unit_of_measurement = "buddies"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="foodsharing.de",
            model="Account",
        )

    @property
    def native_value(self) -> int:
        """Return the number of buddies."""
        data = self.coordinator.data.get("account", {}).get("buddies", [])
        return len(data) if isinstance(data, list) else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return buddy details as attributes."""
        buddies = self.coordinator.data.get("account", {}).get("buddies", [])
        return {
            "buddies": buddies,
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }


class FoodsharingBananasSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Displays the number of received bananas (thank-yous)."""

    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FoodsharingCoordinator, email: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.email = email
        self._attr_has_entity_name = True
        self.translation_key = "bananas"
        self._unique_id_base = f"Foodsharing-Bananas-{email}"
        self._attr_unique_id = self._unique_id_base
        self._attr_icon = "mdi:food-apple"  # No banana icon in MDI
        self._attr_native_unit_of_measurement = "bananas"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="foodsharing.de",
            model="Account",
        )

    @property
    def native_value(self) -> int:
        """Return the number of received bananas."""
        data = self.coordinator.data.get("account", {}).get("bananas", {})
        return data.get("receivedCount", 0) if isinstance(data, dict) else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return banana details as attributes."""
        data = self.coordinator.data.get("account", {}).get("bananas", {})
        return {
            "given": data.get("givenCount", 0),
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }


class FoodsharingRegionStatsSensor(CoordinatorEntity[FoodsharingCoordinator], SensorEntity):  # type: ignore[misc]
    """Displays statistics for the user's home region."""

    def __init__(self, coordinator: FoodsharingCoordinator, email: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.email = email
        self._attr_has_entity_name = True
        self.translation_key = "region_stats"
        self._unique_id_base = f"Foodsharing-Region-Stats-{email}"
        self._attr_unique_id = self._unique_id_base
        self._attr_icon = "mdi:map-outline"
        self._attr_native_unit_of_measurement = "kg"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="foodsharing.de",
            model="Account",
        )
        self.entity_registry_enabled_default = False

    @property
    def native_value(self) -> Any:
        """Return the weight of saved food in the last month."""
        data = self.coordinator.data.get("account", {}).get("region_stats", {})
        return data.get("savedFoodKgLastMonth")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return region statistics as attributes."""
        data = self.coordinator.data.get("account", {}).get("region_stats", {})
        region_id = self.coordinator.region_id
        profile = self.coordinator.data.get("account", {}).get("profile", {})
        region_name = profile.get("regionName")

        return {
            "region_id": region_id,
            "region_name": region_name,
            "foodsavers": data.get("activeHomeRegionFoodsavers"),
            "corporations": data.get("activeCoorporations"),
            "pickups_last_month": data.get("pickupsLastMonth"),
            "fairteiler": data.get("activeFoodSharePoints"),
            "baskets_last_month": data.get("foodBasketsLastMonth"),
            "last_updated": data.get("lastUpdated"),
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }
