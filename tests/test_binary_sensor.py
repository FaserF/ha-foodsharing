"""Tests for Foodsharing binary sensors."""

from unittest.mock import MagicMock

from custom_components.foodsharing.binary_sensor import FoodsharingSleepingHatSensor


def test_sleeping_hat_sensor():
    """Test sleeping hat binary sensor."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {"account": {"profile": {"isSleeping": True}}}

    sensor = FoodsharingSleepingHatSensor(mock_coordinator, "test@example.com")
    assert sensor.translation_key == "sleeping_hat"
    assert sensor.is_on is True

    # Test off state
    mock_coordinator.data["account"]["profile"]["isSleeping"] = False
    assert sensor.is_on is False
