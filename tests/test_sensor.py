from unittest.mock import MagicMock

from custom_components.foodsharing.sensor import (
    FoodsharingBellsSensor,
    FoodsharingMessagesSensor,
    FoodsharingPickupsSensor,
    FoodsharingSensor,
)


def test_sensor_init():
    """Test sensor initialization."""
    mock_coordinator = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {}
    mock_coordinator.email = "test@example.com"

    sensor = FoodsharingSensor(mock_coordinator, mock_entry, loc_idx=0, lat=50.0, lon=10.0)
    assert sensor.name == "Baskets"
    assert sensor._attr_unique_id == f"Foodsharing-Baskets-{mock_entry.entry_id}-0"


def test_messages_sensor():
    """Test messages sensor."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {"account": {"messages": 5}, "locations": {}}

    sensor = FoodsharingMessagesSensor(mock_coordinator, "test@example.com")
    assert sensor.native_value == 5


def test_bells_sensor():
    """Test bells sensor."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {"account": {"bells": 2}, "locations": {}}

    sensor = FoodsharingBellsSensor(mock_coordinator, "test@example.com")
    assert sensor.native_value == 2


def test_pickups_sensor():
    """Test pickups sensor."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "account": {"pickups": [{"id": 1}, {"id": 2}]},
        "locations": {},
    }

    sensor = FoodsharingPickupsSensor(mock_coordinator, "test@example.com")
    assert sensor.native_value == 2
    assert sensor.extra_state_attributes["pickups"] == [{"id": 1}, {"id": 2}]
