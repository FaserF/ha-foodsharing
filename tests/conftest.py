"""Fixtures for testing Foodsharing integration."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def auto_mock_ha():
    """Mock the Home Assistant helpers that require a running instance."""
    with (
        patch("homeassistant.core.HomeAssistant"),
        patch("homeassistant.helpers.frame.report_usage"),
    ):
        yield


@pytest.fixture()
def mock_session():
    """Mock an aiohttp ClientSession."""
    mock = MagicMock()
    return mock
