"""Tests for Foodsharing geo locations."""
from unittest.mock import MagicMock

import pytest

from custom_components.foodsharing.geo_location import (
    FoodsharingBasketGeoLocation,
    FoodsharingFairteilerGeoLocation,
)


@pytest.mark.asyncio
async def test_basket_geo_location_properties():
    """Test basket geo location entity properties."""
    mock_coordinator = MagicMock()
    mock_coordinator.last_update_success = False
    mock_coordinator.data = {
        "baskets": [
            {
                "id": 123,
                "latitude": 50.0,
                "longitude": 10.0,
                "available_until": "18.04. 19:30",
                "keyword_match": True,
            }
        ]
    }
    mock_entry = MagicMock()
    mock_entry.data = {"latitude": "50", "longitude": "10"}

    basket = {
        "id": 123,
        "latitude": 50.0,
        "longitude": 10.0,
        "available_until": "Tomorrow",
        "keyword_match": True,
    }
    entity = FoodsharingBasketGeoLocation(mock_coordinator, mock_entry, basket)
    assert entity.distance is None
    assert entity.extra_state_attributes.get("keyword_match") is True
    assert entity.available is False


@pytest.mark.asyncio
async def test_fairteiler_geo_location_properties():
    """Test fairteiler geo location entity properties."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "fairteiler": [
            {"id": 456, "latitude": 51.0, "longitude": 11.0, "name": "Store"}
        ]
    }
    mock_entry = MagicMock()
    mock_entry.data = {"latitude": "51", "longitude": "11", "email": "test@test.com"}

    fp = {"id": 456, "latitude": 51.0, "longitude": 11.0, "name": "Store"}
    entity = FoodsharingFairteilerGeoLocation(
        mock_coordinator, mock_entry, fp, "456"
    )
    assert entity.distance is None
    assert entity.name == "Fairteiler: Store"
