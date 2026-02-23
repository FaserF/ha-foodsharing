"""Tests for FoodsharingCoordinator."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.foodsharing.coordinator import FoodsharingCoordinator


def _make_entry(data_overrides=None):
    """Create a mock ConfigEntry with all required keys."""
    base_data = {
        "email": "test@test.com",
        "password": "pass",
        "latitude": "50.0",
        "longitude": "10.0",
        "distance": 7,
        "keywords": "",
    }
    if data_overrides:
        base_data.update(data_overrides)
    mock_entry = MagicMock()
    mock_entry.data = base_data
    mock_entry.options = {}
    return mock_entry


@pytest.mark.asyncio
async def test_coordinator_fetch_pickups(mock_session):
    """Test fetching pickups handles different data structures and the correct endpoint."""
    mock_entry = _make_entry()

    with patch(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession",
        return_value=mock_session,
    ):
        coordinator = FoodsharingCoordinator(MagicMock(), mock_entry)

        # 1. Test successful array return from correct endpoint
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = [{"id": 1, "store_name": "Test Store"}]

        mock_session.get.return_value.__aenter__.return_value = mock_response

        pickups = await coordinator.fetch_pickups()
        assert isinstance(pickups, list)
        assert len(pickups) == 1
        assert pickups[0]["store_name"] == "Test Store"
        # Verify endpoint used
        mock_session.get.assert_called_with("https://foodsharing.de/api/pickup/registered")

        # 2. Test successful dictionary return ("pickups" key)
        mock_response.json.return_value = {"pickups": [{"id": 2, "store_name": "Store 2"}]}
        pickups = await coordinator.fetch_pickups()
        assert len(pickups) == 1
        assert pickups[0]["id"] == 2

        # 3. Test successful dictionary return ("data" key)
        mock_response.json.return_value = {"data": [{"id": 3, "store_name": "Store 3"}]}
        pickups = await coordinator.fetch_pickups()
        assert len(pickups) == 1
        assert pickups[0]["id"] == 3


@pytest.mark.asyncio
async def test_coordinator_fetch_conversations(mock_session):
    """Test fetching unread messages handles list format."""
    mock_entry = _make_entry()

    with patch(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession",
        return_value=mock_session,
    ):
        coordinator = FoodsharingCoordinator(MagicMock(), mock_entry)

        # Test conversation list json
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = [{"unread": 1, "last_message": {"id": 10}}]

        mock_count = AsyncMock()
        mock_count.status = 200
        mock_count.json.return_value = {"unread": 1}

        # Need to handle consecutive get calls
        mock_session.get.return_value.__aenter__.side_effect = [mock_count, mock_response]

        unread = await coordinator.fetch_unread_messages()
        assert unread == 1


@pytest.mark.asyncio
async def test_coordinator_fetch_bells(mock_session):
    """Test fetching bells."""
    mock_entry = _make_entry()

    with patch(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession",
        return_value=mock_session,
    ):
        coordinator = FoodsharingCoordinator(MagicMock(), mock_entry)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = [{"is_read": 0, "id": 55}]

        mock_session.get.return_value.__aenter__.return_value = mock_response

        unread = await coordinator.fetch_bells()
        assert unread == 1
