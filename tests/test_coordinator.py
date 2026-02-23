"""Tests for FoodsharingCoordinator."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("custom_components.foodsharing.coordinator")
from custom_components.foodsharing.coordinator import FoodsharingCoordinator


@pytest.mark.asyncio
async def test_coordinator_fetch_pickups(mock_session):
    """Test fetching pickups handles different data structures safely."""

    mock_entry = MagicMock()
    mock_entry.data = {
        "email": "test@test.com",
        "password": "pass",
        "latitude_fs": "50.0",
        "longitude_fs": "10.0",
        "distance": 5
    }
    mock_entry.options = {}

    with patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=mock_session):
        coordinator = FoodsharingCoordinator(MagicMock(), mock_entry)

        # Test successful array return
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = [{"id": 1, "store_name": "Test Store"}]

        mock_session.get.return_value.__aenter__.return_value = mock_response

        pickups = await coordinator.fetch_pickups()
        assert isinstance(pickups, list)
        assert len(pickups) == 1
        assert pickups[0]["store_name"] == "Test Store"

@pytest.mark.asyncio
async def test_coordinator_fetch_conversations(mock_session):
    """Test fetching unread messages handles list format."""
    mock_entry = MagicMock()
    mock_entry.data = {"latitude_fs": "50", "longitude_fs": "10"}
    mock_entry.options = {}

    with patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=mock_session):
        coordinator = FoodsharingCoordinator(MagicMock(), mock_entry)

        # Test conversation list json
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = [{"unread": 1, "last_message": {"id": 10}}]

        mock_count = AsyncMock()
        mock_count.status = 200
        mock_count.json.return_value = {"unread": 1}

        # Need to handle consecutive get calls if possible or just assume it catches errors safely
        mock_session.get.return_value.__aenter__.side_effect = [mock_count, mock_response]

        unread = await coordinator.fetch_unread_messages()
        assert unread == 1

@pytest.mark.asyncio
async def test_coordinator_fetch_bells(mock_session):
    """Test fetching bells."""
    mock_entry = MagicMock()
    mock_entry.data = {"latitude_fs": "50", "longitude_fs": "10"}
    mock_entry.options = {}

    with patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=mock_session):
        coordinator = FoodsharingCoordinator(MagicMock(), mock_entry)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = [{"is_read": 0, "id": 55}]

        mock_session.get.return_value.__aenter__.return_value = mock_response

        unread = await coordinator.fetch_bells()
        assert unread == 1
