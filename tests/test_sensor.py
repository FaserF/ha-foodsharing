from unittest.mock import MagicMock

from custom_components.foodsharing.sensor import (
    FoodsharingBananasSensor,
    FoodsharingBellsSensor,
    FoodsharingBuddiesSensor,
    FoodsharingFairteilerSensor,
    FoodsharingGlobalStatsSensor,
    FoodsharingMessagesSensor,
    FoodsharingPickupsSensor,
    FoodsharingRegionStatsSensor,
    FoodsharingSensor,
    FoodsharingUserStatsSensor,
)


def test_sensor_init():
    """Test sensor initialization."""
    mock_coordinator = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {}
    mock_coordinator.email = "test@example.com"

    sensor = FoodsharingSensor(
        mock_coordinator, mock_entry, loc_idx=0, lat=50.0, lon=10.0
    )
    assert sensor.translation_key == "baskets"
    assert sensor._attr_unique_id == f"Foodsharing-Baskets-{mock_entry.entry_id}-0"


def test_messages_sensor():
    """Test messages sensor."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {"account": {"messages": 5}, "locations": {}}

    sensor = FoodsharingMessagesSensor(mock_coordinator, "test@example.com")
    assert sensor.translation_key == "unread_messages"
    assert sensor.native_value == 5


def test_bells_sensor():
    """Test bells sensor."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {"account": {"bells": 2}, "locations": {}}

    sensor = FoodsharingBellsSensor(mock_coordinator, "test@example.com")
    assert sensor.translation_key == "notifications"
    assert sensor.native_value == 2


def test_pickups_sensor():
    """Test pickups sensor."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "account": {"pickups": [{"id": 1}, {"id": 2}]},
        "locations": {},
    }

    sensor = FoodsharingPickupsSensor(mock_coordinator, "test@example.com")
    assert sensor.translation_key == "upcoming_pickups"
    assert sensor.native_value == 2
    assert sensor.extra_state_attributes["pickups"] == [{"id": 1}, {"id": 2}]


def test_fairteiler_sensor():
    """Test fairteiler sensor."""
    mock_coordinator = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_coordinator.data = {
        "locations": {
            "test_entry": [
                {
                    "fairteiler": [
                        {"id": 1, "name": "FT 1"},
                        {"id": 2, "name": "FT 2"},
                    ]
                }
            ]
        }
    }

    sensor = FoodsharingFairteilerSensor(
        mock_coordinator, mock_entry, loc_idx=0, lat=50.0, lon=10.0
    )
    assert sensor.translation_key == "fairteiler"
    assert sensor.native_value == 2
    assert len(sensor.extra_state_attributes["fairteiler"]) == 2


def test_global_stats_sensor():
    """Test global stats sensor."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "account": {
            "global_stats": {
                "fetchWeight": 1234.5,
                "fetchCount": 100,
            }
        }
    }

    sensor = FoodsharingGlobalStatsSensor(mock_coordinator, "test@example.com")
    assert sensor.translation_key == "global_stats"
    assert sensor.native_value == 1234.5
    assert sensor.extra_state_attributes["rescue_missions"] == 100
    assert sensor.entity_registry_enabled_default is False


def test_user_stats_sensor():
    """Test user stats sensor."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "account": {
            "user_stats": {
                "fetchWeight": 50.0,
                "pickup_count": 10,
            }
        }
    }

    sensor = FoodsharingUserStatsSensor(mock_coordinator, "test@example.com")
    assert sensor.translation_key == "user_stats"
    assert sensor.native_value == 10
    assert sensor.extra_state_attributes["weight_saved_kg"] == 50.0


def test_buddies_sensor():
    """Test buddies sensor."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {"account": {"buddies": [{"id": 1}, {"id": 2}]}}

    sensor = FoodsharingBuddiesSensor(mock_coordinator, "test@example.com")
    assert sensor.translation_key == "buddies"
    assert sensor.native_value == 2
    assert len(sensor.extra_state_attributes["buddies"]) == 2


def test_bananas_sensor():
    """Test bananas sensor."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "account": {"bananas": {"receivedCount": 5, "givenCount": 3}}
    }

    sensor = FoodsharingBananasSensor(mock_coordinator, "test@example.com")
    assert sensor.translation_key == "bananas"
    assert sensor.native_value == 5
    assert sensor.extra_state_attributes["given"] == 3


def test_region_stats_sensor():
    """Test region stats sensor."""
    mock_coordinator = MagicMock()
    mock_coordinator.region_id = 123
    mock_coordinator.data = {
        "account": {
            "profile": {"regionName": "Muenster"},
            "region_stats": {
                "savedFoodKgLastMonth": 1000,
                "activeHomeRegionFoodsavers": 500,
            },
        }
    }

    sensor = FoodsharingRegionStatsSensor(mock_coordinator, "test@example.com")
    assert sensor.translation_key == "region_stats"
    assert sensor.native_value == 1000
    assert sensor.extra_state_attributes["region_name"] == "Muenster"
    assert sensor.extra_state_attributes["foodsavers"] == 500
    assert sensor.entity_registry_enabled_default is False
