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
        "account": {},
        "locations": {
            "entry_1": [
                {
                    "baskets": [
                        {
                            "id": 123,
                            "latitude": 50.0,
                            "longitude": 10.0,
                            "available_until": "18.04. 19:30",
                            "keyword_match": True,
                        }
                    ],
                    "fairteiler": [],
                }
            ]
        },
    }
    mock_entry = MagicMock()
    mock_entry.data = {"latitude": "50", "longitude": "10"}
    mock_entry.entry_id = "entry_1"

    basket = {
        "id": 123,
        "latitude": 50.0,
        "longitude": 10.0,
        "available_until": "Tomorrow",
        "keyword_match": True,
    }
    email = "test@example.com"
    entity = FoodsharingBasketGeoLocation(
        mock_coordinator, mock_entry, basket, loc_idx=0, home_lat=50.0, home_lon=10.0, email=email
    )
    assert entity.distance == 0.0
    assert entity.extra_state_attributes.get("keyword_match") is True
    assert entity.available is False


@pytest.mark.asyncio
async def test_fairteiler_geo_location_properties():
    """Test fairteiler geo location entity properties."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "account": {},
        "locations": {
            "entry_1": [
                {
                    "baskets": [],
                    "fairteiler": [
                        {"id": 456, "latitude": 51.0, "longitude": 11.0, "name": "Store"}
                    ],
                }
            ]
        },
    }
    mock_entry = MagicMock()
    mock_entry.data = {"latitude": "51", "longitude": "11", "email": "test@test.com"}
    mock_entry.entry_id = "entry_1"

    fp = {"id": 456, "latitude": 51.0, "longitude": 11.0, "name": "Store"}
    email = "test@test.com"
    entity = FoodsharingFairteilerGeoLocation(
        mock_coordinator, mock_entry, fp, loc_idx=0, unique_id="fp_456", home_lat=51.0, home_lon=11.0, email=email
    )
    assert entity.distance == 0.0
    assert entity.name == "Fairteiler: Store"
