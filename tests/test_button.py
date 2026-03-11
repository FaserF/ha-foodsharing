"""Test button platform for Foodsharing."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.foodsharing.button import (
    FoodsharingCloseSlotButton,
    FoodsharingRequestSlotButton,
)


@pytest.fixture
def mock_coordinator():
    """Mock coordinator."""
    coordinator = MagicMock()
    coordinator.email = "test@example.com"
    coordinator.last_update_success = True
    coordinator.base_url = "https://foodsharing.de"
    coordinator._headers = {"Authorization": "Bearer test"}

    # Mock session and post
    coordinator.session = MagicMock()
    
    # helper for creating a response mock
    def create_mock_response(status=200):
        mock_resp = MagicMock()
        mock_resp.status = status
        # context manager mocks
        response_cm = AsyncMock()
        response_cm.__aenter__.return_value = mock_resp
        return response_cm

    coordinator.session.post.return_value = create_mock_response(200)
    
    coordinator.async_request_refresh = AsyncMock(return_value=None)

    # Mock data structure
    coordinator.data = {
        "account": {
            "own_baskets": [
                {"id": "own_1", "description": "My Basket 1"},
                {"id": "own_2", "description": "My Basket 2"},
            ]
        },
        "locations": {
            "entry_1": [
                {
                    "latitude": 52.0,
                    "longitude": 13.0,
                    "baskets": [
                        {"id": "basket_1", "description": "Fresh Bread"},
                        {"id": "basket_2", "description": "Apples"},
                    ],
                }
            ]
        },
    }
    return coordinator


@pytest.fixture
def mock_entry():
    """Mock config entry."""
    entry = MagicMock()
    entry.entry_id = "entry_1"
    return entry


def test_request_button_slot(mock_coordinator, mock_entry):
    """Test the request basket slot button."""
    # Test slot 0 (occupied)
    button0 = FoodsharingRequestSlotButton(
        mock_coordinator, mock_entry, loc_idx=0, lat=52.0, lon=13.0, slot_idx=0
    )
    assert button0.available is True
    assert button0.name == "Request Basket 1: Fresh Bread..."
    assert button0._attr_unique_id == "foodsharing_entry_1_loc_0_request_basket_0"

    # Test slot 1 (occupied)
    button1 = FoodsharingRequestSlotButton(
        mock_coordinator, mock_entry, loc_idx=0, lat=52.0, lon=13.0, slot_idx=1
    )
    assert button1.available is True
    assert button1.name == "Request Basket 2: Apples..."

    # Test slot 2 (empty)
    button2 = FoodsharingRequestSlotButton(
        mock_coordinator, mock_entry, loc_idx=0, lat=52.0, lon=13.0, slot_idx=2
    )
    assert button2.available is False
    assert button2.name == "Request Basket 3 (Empty Slot)"


@pytest.mark.asyncio
async def test_request_button_press(mock_coordinator, mock_entry):
    """Test pressing the request button."""
    button = FoodsharingRequestSlotButton(
        mock_coordinator, mock_entry, loc_idx=0, lat=52.0, lon=13.0, slot_idx=0
    )

    await button.async_press()

    mock_coordinator.session.post.assert_called_once_with(
        "https://foodsharing.de/api/baskets/basket_1/request",
        headers={"Authorization": "Bearer test"},
    )
    mock_coordinator.async_request_refresh.assert_called_once()


def test_close_button_slot(mock_coordinator):
    """Test the close own basket slot button."""
    # Test slot 0 (occupied)
    button0 = FoodsharingCloseSlotButton(
        mock_coordinator, email="test@example.com", slot_idx=0
    )
    assert button0.available is True
    assert button0.name == "Close Own Basket 1: My Basket 1..."
    assert button0._attr_unique_id == "foodsharing_test@example.com_close_basket_0"

    # Test slot 2 (empty)
    button2 = FoodsharingCloseSlotButton(
        mock_coordinator, email="test@example.com", slot_idx=2
    )
    assert button2.available is False
    assert button2.name == "Close Own Basket 3 (Empty Slot)"


@pytest.mark.asyncio
async def test_close_button_press(mock_coordinator):
    """Test pressing the close button."""
    button = FoodsharingCloseSlotButton(
        mock_coordinator, email="test@example.com", slot_idx=0
    )

    await button.async_press()

    mock_coordinator.session.post.assert_called_once_with(
        "https://foodsharing.de/api/baskets/own_1/close",
        headers={"Authorization": "Bearer test"},
    )
    mock_coordinator.async_request_refresh.assert_called_once()
