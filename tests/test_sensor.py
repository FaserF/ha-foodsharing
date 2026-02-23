"""Tests for Foodsharing sensors."""
import pytest
from unittest.mock import MagicMock
from custom_components.foodsharing.sensor import FoodsharingSensor, FoodsharingMessagesSensor, FoodsharingBellsSensor

def test_sensor_init():
    """Test sensor initialization."""
    mock_coordinator = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {}
    mock_coordinator.hass.config.latitude = 50.0
    mock_coordinator.hass.config.longitude = 10.0

    sensor = FoodsharingSensor(mock_coordinator, mock_entry)
    assert sensor.name == "Foodsharing Baskets 50.0"

def test_messages_sensor():
    """Test messages sensor."""
    mock_coordinator = MagicMock()
    mock_entry = MagicMock()
    mock_coordinator.data = {"messages": 5}

    sensor = FoodsharingMessagesSensor(mock_coordinator, mock_entry)
    assert sensor.state == 5

def test_bells_sensor():
    """Test bells sensor."""
    mock_coordinator = MagicMock()
    mock_entry = MagicMock()
    mock_coordinator.data = {"bells": 2}

    sensor = FoodsharingBellsSensor(mock_coordinator, mock_entry)
    assert sensor.state == 2
