"""Button platform for Foodsharing, with dynamic entity management."""

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
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

# Global registry to track active button entities across multiple config entries for the same account (email).
# Format: { email: { unique_id: ButtonEntity } }
ACTIVE_BUTTONS: dict[str, dict[str, ButtonEntity]] = {}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the foodsharing button platform."""
    coordinator: FoodsharingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    email = coordinator.email

    # Get or create the account-wide button registry for this email
    if email not in ACTIVE_BUTTONS:
        ACTIVE_BUTTONS[email] = {}
    active_buttons = ACTIVE_BUTTONS[email]

    @callback
    def async_update_entities() -> None:
        """Update active buttons based on available baskets."""
        if not coordinator.data:
            return

        new_entities: list[ButtonEntity] = []
        current_unique_ids: set[str] = set()

        # 1. Request Basket Buttons (per location)
        locations = get_locations_from_entry(entry)
        entry_locs: list[dict[str, Any]] = (
            coordinator.data.get("locations", {}).get(entry.entry_id, [])
        )

        for loc_idx, loc in enumerate(locations):
            if loc_idx >= len(entry_locs):
                continue

            baskets = entry_locs[loc_idx].get("baskets", [])
            lat = loc["latitude"]
            lon = loc["longitude"]

            for slot_idx in range(len(baskets)):
                unique_id = f"foodsharing_{entry.entry_id}_loc_{loc_idx}_request_basket_{slot_idx}"
                current_unique_ids.add(unique_id)

                if unique_id not in active_buttons:
                    button = FoodsharingRequestSlotButton(
                        coordinator, entry, loc_idx, lat, lon, slot_idx
                    )
                    active_buttons[unique_id] = button
                    new_entities.append(button)

        # 2. Close Own Basket Buttons (account-wide)
        account_data = coordinator.data.get("account", {})
        own_baskets = account_data.get("own_baskets", [])
        for slot_idx in range(len(own_baskets)):
            unique_id = f"foodsharing_{email}_close_basket_{slot_idx}"
            current_unique_ids.add(unique_id)

            if unique_id not in active_buttons:
                close_button = FoodsharingCloseSlotButton(
                    coordinator, email, slot_idx
                )
                active_buttons[unique_id] = close_button
                new_entities.append(close_button)

        if new_entities:
            async_add_entities(new_entities)

        # 3. Remove stale buttons (if baskets decreased)
        # We only clean up buttons that belong to THIS entry or THIS account's global buttons
        stale_ids = {
            uid for uid, btn in active_buttons.items()
            if (
                getattr(btn, "config_entry_id", None) == entry.entry_id
                or getattr(btn, "account_email", None) == email
            )
            and uid not in current_unique_ids
        }
        if stale_ids:
            registry = er.async_get(hass)
            for uid in stale_ids:
                stale_button = active_buttons.pop(uid)
                # Remove from HASS
                hass.async_create_task(stale_button.async_remove())
                # Also remove from registry so it doesn't show up as 'restored'
                entity_id = registry.async_get_entity_id("button", DOMAIN, uid)
                if entity_id:
                    registry.async_remove(entity_id)

    # Initial sync
    async_update_entities()

    # Register listener
    unsub = coordinator.async_add_listener(async_update_entities)
    entry.async_on_unload(unsub)

    # Ensure cleanup on unload from the global registry if this was the last entry
    @callback
    def async_on_unload() -> None:
        if not coordinator.entries and email in ACTIVE_BUTTONS:
            ACTIVE_BUTTONS.pop(email)

    entry.async_on_unload(async_on_unload)


class FoodsharingRequestSlotButton(CoordinatorEntity[FoodsharingCoordinator], ButtonEntity):  # type: ignore[misc]
    """A dynamic button slot that requests the N-th available basket for a location."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FoodsharingCoordinator,
        entry: ConfigEntry,
        loc_idx: int,
        lat: float,
        lon: float,
        slot_idx: int,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entry = entry
        self._loc_idx = loc_idx
        self._lat = lat
        self._lon = lon
        self._slot_idx = slot_idx

        self._attr_unique_id = (
            f"foodsharing_{entry.entry_id}_loc_{loc_idx}_request_basket_{slot_idx}"
        )
        self.translation_key = "request_basket"
        self.config_entry_id = entry.entry_id
        self._attr_icon = "mdi:cart-plus"

        email = coordinator.email
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{email}_{lat}_{lon}")},
            name=f"Foodsharing Location ({lat}, {lon})",
            manufacturer="Foodsharing",
            model="Location Tracker",
            via_device=(DOMAIN, email),
        )

    def _get_basket(self) -> dict[str, Any] | None:
        """Get the basket currently occupying this slot."""
        if not self.coordinator.data:
            return None

        entry_locs: list[dict[str, Any]] = (
            self.coordinator.data.get("locations", {}).get(self.entry.entry_id, [])
        )
        if self._loc_idx >= len(entry_locs):
            return None

        baskets = entry_locs[self._loc_idx].get("baskets", [])
        if self._slot_idx < len(baskets):
            basket = baskets[self._slot_idx]
            if isinstance(basket, dict):
                return basket
        return None

    @property
    def available(self) -> bool:
        """Return True if the slot is occupied by a basket."""
        return super().available and self._get_basket() is not None

    @property
    def name(self) -> str:
        """Return the static name of the button."""
        basket = self._get_basket()
        if basket:
            return f"Request Basket {self._slot_idx + 1}: {basket.get('description', 'No description')[:20]}..."
        return f"Request Basket {self._slot_idx + 1} (Empty Slot)"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for the basket."""
        basket = self._get_basket()
        if not basket:
            return {}
        return {
            "basket_id": basket.get("id"),
            "description": basket.get("description"),
            "available_until": basket.get("available_until"),
            "picture": basket.get("picture"),
            "latitude": basket.get("latitude"),
            "longitude": basket.get("longitude"),
            "maps": basket.get("maps"),
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        basket = self._get_basket()
        if not basket:
            _LOGGER.warning("Slot %s has no active basket to request.", self._slot_idx)
            return

        basket_id = str(basket["id"])
        _LOGGER.info("Button pressed to request basket %s (Slot %s)", basket_id, self._slot_idx)

        url = f"{self.coordinator.base_url}/api/baskets/{basket_id}/request"
        try:
            async with self.coordinator.session.post(url, headers=self.coordinator._headers) as response:
                if response.status == 200:
                    _LOGGER.info("Successfully requested basket %s", basket_id)
                    await self.coordinator.async_request_refresh()
                else:
                    _LOGGER.error(
                        "Failed to request basket %s. Status: %s",
                        basket_id,
                        response.status,
                    )
        except Exception as e:
            _LOGGER.error("Exception requesting basket: %s", e)


class FoodsharingCloseSlotButton(CoordinatorEntity[FoodsharingCoordinator], ButtonEntity):  # type: ignore[misc]
    """A dynamic button slot that closes the N-th active own basket for the account."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FoodsharingCoordinator,
        email: str,
        slot_idx: int,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.email = email
        self._slot_idx = slot_idx

        self._attr_unique_id = f"foodsharing_{email}_close_basket_{slot_idx}"
        self.translation_key = "close_own_basket"
        self.account_email = email
        self._attr_icon = "mdi:cart-off"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="Foodsharing",
            model="Account",
        )

    def _get_basket(self) -> dict[str, Any] | None:
        """Get the own-basket currently occupying this slot."""
        if not self.coordinator.data:
            return None

        account_data = self.coordinator.data.get("account", {})
        own_baskets = account_data.get("own_baskets", [])
        if self._slot_idx < len(own_baskets):
            basket = own_baskets[self._slot_idx]
            if isinstance(basket, dict):
                return basket
        return None
    @property
    def available(self) -> bool:
        """Return True if the slot is occupied by a basket."""
        return super().available and self._get_basket() is not None

    @property
    def name(self) -> str:
        """Return the static name of the button."""
        basket = self._get_basket()
        if basket:
            return f"Close Own Basket {self._slot_idx + 1}: {basket.get('description', 'No description')[:20]}..."
        return f"Close Own Basket {self._slot_idx + 1} (Empty Slot)"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for the own basket."""
        basket = self._get_basket()
        if not basket:
            return {}
        return {
            "basket_id": basket.get("id"),
            "description": basket.get("description"),
            "picture": basket.get("picture"),
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        basket = self._get_basket()
        if not basket:
            _LOGGER.warning("Slot %s has no active own basket to close.", self._slot_idx)
            return

        basket_id = str(basket["id"])
        _LOGGER.info("Button pressed to close own basket %s (Slot %s)", basket_id, self._slot_idx)

        url = f"{self.coordinator.base_url}/api/baskets/{basket_id}/close"
        try:
            async with self.coordinator.session.post(url, headers=self.coordinator._headers) as response:
                if response.status == 200:
                    _LOGGER.info("Successfully closed own basket %s", basket_id)
                    await self.coordinator.async_request_refresh()
                else:
                    _LOGGER.error(
                        "Failed to close own basket %s. Status: %s",
                        basket_id,
                        response.status,
                    )
        except Exception as e:
            _LOGGER.error("Exception closing own basket: %s", e)
