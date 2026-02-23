"""Fixtures for testing Foodsharing integration."""
import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture(autouse=True)
def auto_mock_ha():
    """Mock the Home Assistant core imports to run tests without starting HA."""
    with patch("homeassistant.core.HomeAssistant") as mock_hass:
        yield mock_hass

@pytest.fixture()
def mock_session():
    """Mock an aiohttp ClientSession."""
    mock = MagicMock()
    # Basic mocking if needed
    return mock
