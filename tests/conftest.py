"""Fixtures for testing Foodsharing integration."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def auto_mock_ha():
    """Mock the Home Assistant helpers that require a running instance."""
    import homeassistant.helpers.frame as frame

    with (
        patch("homeassistant.core.HomeAssistant"),
        patch("homeassistant.helpers.frame.report") if hasattr(frame, "report") else patch("homeassistant.core.HomeAssistant"),
        patch("homeassistant.helpers.frame.report_usage") if hasattr(frame, "report_usage") else patch("homeassistant.core.HomeAssistant"),
    ):
        yield


@pytest.fixture()
def mock_session():
    """Mock an aiohttp ClientSession."""
    mock = MagicMock()
    return mock
