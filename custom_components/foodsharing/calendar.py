"""Calendar platform for Foodsharing integration."""

import logging
from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
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
    email = hass.data[DOMAIN][entry.entry_id]["email"]

    account_key = f"calendars_{email}"
    if account_key not in hass.data[DOMAIN]:
        hass.data[DOMAIN][account_key] = True
        async_add_entities([FoodsharingCalendar(coordinator, email)])


class FoodsharingCalendar(CoordinatorEntity[FoodsharingCoordinator], CalendarEntity):  # type: ignore[misc]
    """A calendar entity for foodsharing pickups."""

    def __init__(self, coordinator: FoodsharingCoordinator, email: str) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator)
        self.email = email

        self.translation_key = "pickups"
        self._attr_unique_id = f"foodsharing_calendar_{email}"
        self._events: list[CalendarEvent] = []

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, email)},
            name=f"Foodsharing Account ({email})",
            manufacturer="foodsharing.de",
            model="Account",
        )

        self._process_events()

    def _process_events(self) -> None:
        """Process the events from the coordinator data."""
        self._events = []
        if self.coordinator.data is None:
            return

        account_data = self.coordinator.data.get("account", {})
        pickups = account_data.get("pickups", [])
        if not isinstance(pickups, list):
            return

        for pickup in pickups:
            start_ts = pickup.get("time")
            if start_ts is None:
                start_ts = pickup.get("date")

            if start_ts is None:
                continue

            try:
                ts_val = float(start_ts)
                start_dt = dt_util.as_local(dt_util.utc_from_timestamp(ts_val))
                end_dt = dt_util.as_local(dt_util.utc_from_timestamp(ts_val + 3600.0))

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

        upcoming_events = [e for e in self._events if e.end > now]
        if not upcoming_events:
            return None

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
