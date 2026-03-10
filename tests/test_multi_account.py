"""Tests for multi-account and location support."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.foodsharing import async_setup_entry
from custom_components.foodsharing.const import (
    CONF_EMAIL,
    CONF_LATITUDE_FS,
    CONF_LOCATIONS,
    CONF_LONGITUDE_FS,
    CONF_PASSWORD,
    DOMAIN,
)
from custom_components.foodsharing.helpers import get_locations_from_entry, parse_extra_locations


@pytest.fixture
def mock_hass():
    """Mock HomeAssistant."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {DOMAIN: {"accounts": {}}}
    return hass

@pytest.mark.asyncio
async def test_shared_coordinator_same_account(mock_hass, mock_session):
    """Test that two locations for the same account share a coordinator."""
    with patch("custom_components.foodsharing.coordinator.async_get_clientsession", return_value=mock_session), \
         patch("custom_components.foodsharing.coordinator.FoodsharingCoordinator.async_config_entry_first_refresh", return_value=None), \
         patch("custom_components.foodsharing.coordinator.FoodsharingCoordinator.async_request_refresh", new_callable=AsyncMock), \
         patch("custom_components.foodsharing.dr.async_get", return_value=MagicMock()):

        entry1 = MagicMock()
        entry1.entry_id = "entry1"
        entry1.data = {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "pw",
                       CONF_LOCATIONS: [{"latitude": 50.0, "longitude": 10.0, "distance": 7}]}
        entry1.options = {}

        entry2 = MagicMock()
        entry2.entry_id = "entry2"
        entry2.data = {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "pw",
                       CONF_LOCATIONS: [{"latitude": 51.0, "longitude": 11.0, "distance": 5}]}
        entry2.options = {}

        await async_setup_entry(mock_hass, entry1)
        assert "user@example.com" in mock_hass.data[DOMAIN]["accounts"]
        coord1 = mock_hass.data[DOMAIN]["accounts"]["user@example.com"]

        await async_setup_entry(mock_hass, entry2)
        coord2 = mock_hass.data[DOMAIN]["accounts"]["user@example.com"]

        assert coord1 is coord2
        assert len(coord1.entries) == 2

@pytest.mark.asyncio
async def test_separate_coordinators_different_accounts(mock_hass, mock_session):
    """Test that different accounts get different coordinators."""
    with patch("custom_components.foodsharing.coordinator.async_get_clientsession", return_value=mock_session), \
         patch("custom_components.foodsharing.coordinator.FoodsharingCoordinator.async_config_entry_first_refresh", return_value=None), \
         patch("custom_components.foodsharing.dr.async_get", return_value=MagicMock()):

        entry1 = MagicMock()
        entry1.entry_id = "acc1"
        entry1.data = {CONF_EMAIL: "user1@example.com", CONF_PASSWORD: "pw",
                       CONF_LOCATIONS: [{"latitude": 50.0, "longitude": 10.0, "distance": 7}]}
        entry1.options = {}

        entry2 = MagicMock()
        entry2.entry_id = "acc2"
        entry2.data = {CONF_EMAIL: "user2@example.com", CONF_PASSWORD: "pw",
                       CONF_LOCATIONS: [{"latitude": 50.0, "longitude": 10.0, "distance": 7}]}
        entry2.options = {}

        await async_setup_entry(mock_hass, entry1)
        await async_setup_entry(mock_hass, entry2)

        assert mock_hass.data[DOMAIN]["accounts"]["user1@example.com"] is not \
               mock_hass.data[DOMAIN]["accounts"]["user2@example.com"]


def test_get_locations_from_entry_new_format():
    """Test helper with new locations-list format."""
    entry = MagicMock()
    entry.options = {}
    entry.data = {
        CONF_LOCATIONS: [
            {"latitude": 48.0, "longitude": 11.5, "distance": 5},
            {"latitude": 52.5, "longitude": 13.4, "distance": 7},
        ]
    }
    locs = get_locations_from_entry(entry)
    assert len(locs) == 2
    assert locs[0]["latitude"] == 48.0
    assert locs[1]["longitude"] == 13.4


def test_get_locations_from_entry_legacy_format():
    """Test helper falls back to flat keys for pre-v5 entries."""
    entry = MagicMock()
    entry.options = {}
    entry.data = {CONF_LATITUDE_FS: 48.0, CONF_LONGITUDE_FS: 11.5, "distance": 5}
    locs = get_locations_from_entry(entry)
    assert len(locs) == 1
    assert locs[0]["latitude"] == 48.0


def test_parse_extra_locations():
    """Test parsing of the extra_locations text field."""
    text = "48.12, 11.68, 5; 52.52, 13.41"
    locs = parse_extra_locations(text)
    assert len(locs) == 2
    assert locs[0] == {"latitude": 48.12, "longitude": 11.68, "distance": 5}
    assert locs[1] == {"latitude": 52.52, "longitude": 13.41, "distance": 7}  # default


def test_parse_extra_locations_invalid_entries():
    """Test that invalid entries are skipped gracefully."""
    text = "bad;  ; 48.0,11.5,3"
    locs = parse_extra_locations(text)
    assert len(locs) == 1
    assert locs[0]["distance"] == 3
