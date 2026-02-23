"""Calendar platform for Foodsharing integration."""

import logging
from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import FoodsharingCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the calendar platform."""
    coordinator: FoodsharingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    async_add_entities(
        [FoodsharingCalendar(coordinator, entry)], update_before_add=True
    )


class FoodsharingCalendar(CoordinatorEntity[FoodsharingCoordinator], CalendarEntity):  # type: ignore[misc]
    """A calendar entity for foodsharing pickups."""

    def __init__(self, coordinator: FoodsharingCoordinator, entry: ConfigEntry) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator)
        self.entry = entry

        self._attr_name = "Foodsharing Pickups"
        self._attr_unique_id = f"foodsharing_calendar_{entry.entry_id}"
        self._events: list[CalendarEvent] = []

        # Account Device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data.get("email", ""))},
            "name": f"Foodsharing Account ({entry.data.get('email', '')})",
            "manufacturer": "Foodsharing.de",
            "model": "Account",
        }

        # We process the events whenever coordinator updates
        self._process_events()

    def _process_events(self) -> None:
        """Process the events from the coordinator data."""
        self._events = []
        if self.coordinator.data is None or "pickups" not in self.coordinator.data:
            return

        for pickup in self.coordinator.data["pickups"]:
            # Pickups usually have 'time' or 'date', parsing dependent on API format
            # In absence of exact structure, we'll try to extract timestamp blocks.
            start_ts = pickup.get("time")
            if start_ts is None:
                start_ts = pickup.get("date")

            if start_ts is None:
                continue

            try:
                start_dt = dt_util.as_local(dt_util.utc_from_timestamp(start_ts))
                # Assuming 1 hour slot
                end_dt = dt_util.as_local(dt_util.utc_from_timestamp(start_ts + 3600))

                event = CalendarEvent(
                    start=start_dt,
                    end=end_dt,
                    summary=f"Pickup: {pickup.get('store_name', 'Unknown')}",
                    description=pickup.get("description", ""),
                    location=pickup.get("location", ""),
                )
                self._events.append(event)
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Could not parse pickup time: %s", e)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._process_events()
        super()._handle_coordinator_update()

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        if not self._events:
            return None

        now = dt_util.now()

        # Find the first event that ends after 'now'
        upcoming_events = [e for e in self._events if e.end > now]
        if not upcoming_events:
            return None

        # Return the earliest one
        upcoming_events.sort(key=lambda x: x.start)
        return upcoming_events[0]

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        return [
            event
            for event in self._events
            if event.end > start_date and event.start < end_date
        ]
