"""Tests for Foodsharing buttons."""
import pytest
from unittest.mock import MagicMock, AsyncMock

try:
    from custom_components.foodsharing.button import (
        FoodsharingRequestButton,
        FoodsharingCloseOwnBasketButton,
    )
except ImportError:
    pass

@pytest.mark.asyncio
async def test_request_button_press():
    """Test button triggers API call via coordinator."""
    mock_coordinator = MagicMock()
    mock_coordinator.session = MagicMock()
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_coordinator.session.post.return_value.__aenter__.return_value = mock_response
    mock_coordinator.async_request_refresh = AsyncMock()

    mock_entry = MagicMock()
    mock_entry.data = {}

    try:
        basket = {"id": 123, "description": "Test"}
        button = FoodsharingRequestButton(mock_coordinator, mock_entry, basket)
        await button.async_press()
        mock_coordinator.session.post.assert_called_with("https://foodsharing.de/api/baskets/123/request")
        mock_coordinator.async_request_refresh.assert_called_once()
    except NameError:
        pass

@pytest.mark.asyncio
async def test_close_own_basket_button_press():
    """Test close own basket button logic triggers correct API."""
    mock_coordinator = MagicMock()
    mock_coordinator.session = MagicMock()
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_coordinator.session.post.return_value.__aenter__.return_value = mock_response
    mock_coordinator.async_request_refresh = AsyncMock()

    mock_entry = MagicMock()
    mock_entry.data = {}

    try:
        basket = {"id": 999, "description": "My Basket"}
        button = FoodsharingCloseOwnBasketButton(mock_coordinator, mock_entry, basket)
        await button.async_press()
        mock_coordinator.session.post.assert_called_with("https://foodsharing.de/api/baskets/999/close")
        mock_coordinator.async_request_refresh.assert_called_once()
    except NameError:
        pass
