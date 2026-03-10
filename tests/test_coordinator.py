"""Tests for FoodsharingCoordinator."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.foodsharing.coordinator import AuthenticationFailed, FoodsharingCoordinator


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
        "custom_components.foodsharing.coordinator.async_get_clientsession",
        return_value=mock_session,
    ):
        coordinator = FoodsharingCoordinator(MagicMock(), "test@test.com", "pass")

        # 1. Test successful array return from correct endpoint
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = [{"id": 1, "store_name": "Test Store"}]

        mock_session.get.return_value.__aenter__.return_value = mock_response

        pickups = await coordinator.fetch_pickups()
        assert isinstance(pickups, list)
        assert len(pickups) == 1
        assert pickups[0]["store_name"] == "Test Store"
        # Verify endpoint and headers
        mock_session.get.assert_called_with(
            "https://foodsharing.de/api/users/current/pickups/registered",
            headers={},
        )

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
    with patch(
        "custom_components.foodsharing.coordinator.async_get_clientsession",
        return_value=mock_session,
    ):
        coordinator = FoodsharingCoordinator(MagicMock(), "test@test.com", "pass")

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
    with patch(
        "custom_components.foodsharing.coordinator.async_get_clientsession",
        return_value=mock_session,
    ):
        coordinator = FoodsharingCoordinator(MagicMock(), "test@test.com", "pass")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = [{"is_read": 0, "id": 55}]

        mock_session.get.return_value.__aenter__.return_value = mock_response

        unread = await coordinator.fetch_bells()
        assert unread == 1

@pytest.mark.asyncio
async def test_coordinator_beta_api_url(mock_session):
    """Test that coordinator switch base_url when Beta API is enabled."""
    hass = MagicMock()
    # 1. Start with no beta
    coordinator = FoodsharingCoordinator(hass, "test@test.com", "pass")
    assert coordinator.base_url == "https://foodsharing.de"

    # 2. Add entry with beta enabled
    mock_entry = _make_entry({"use_beta_api": True})
    mock_entry.entry_id = "beta_entry"
    coordinator.add_entry(mock_entry)
    assert coordinator.base_url == "https://beta.foodsharing.de"

    # 3. Remove entry
    coordinator.remove_entry("beta_entry")
    assert coordinator.base_url == "https://foodsharing.de"

@pytest.mark.asyncio
async def test_coordinator_refresh_interval_update(mock_session):
    """Test that coordinator updates its refresh interval correctly."""
    hass = MagicMock()
    coordinator = FoodsharingCoordinator(hass, "test@test.com", "pass")
    
    # Default is 2 minutes (set in __init__)
    # After add_entry, it should take the value from data/options
    mock_entry = _make_entry({"scan_interval": 5})
    mock_entry.entry_id = "test_entry"
    
    coordinator.add_entry(mock_entry)
    from datetime import timedelta
    assert coordinator.update_interval == timedelta(minutes=5)

@pytest.mark.asyncio
async def test_coordinator_fetch_bells_fires_event(mock_session, hass):
    """Test that fetch_bells fires an event for new notifications."""
    with patch(
        "custom_components.foodsharing.coordinator.async_get_clientsession",
        return_value=mock_session,
    ):
        coordinator = FoodsharingCoordinator(hass, "test@test.com", "pass")
        coordinator._is_first_update = False # Force event trigger

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = [
            {"is_read": 0, "id": 101, "title": "New Bell"}
        ]
        mock_session.get.return_value.__aenter__.return_value = mock_response

        # Mock bus.async_fire
        hass.bus.async_fire = MagicMock()

        await coordinator.fetch_bells()
        
        # Verify event was fired
        hass.bus.async_fire.assert_called_once()
        args, _ = hass.bus.async_fire.call_args
        assert args[0] == "foodsharing_new_bell"
        assert args[1]["id"] == 101


@pytest.mark.asyncio
async def test_coordinator_fetch_all_data_auth_propagation(mock_session):
    """Test that _fetch_all_data propagates AuthenticationFailed."""
    with patch(
        "custom_components.foodsharing.coordinator.async_get_clientsession",
        return_value=mock_session,
    ):
        coordinator = FoodsharingCoordinator(MagicMock(), "test@test.com", "pass")

        # Mock a 401 response for one of the fetch calls
        mock_auth_failed = AsyncMock()
        mock_auth_failed.status = 401

        mock_session.get.return_value.__aenter__.return_value = mock_auth_failed

        with pytest.raises(AuthenticationFailed):
            await coordinator._fetch_all_data()
