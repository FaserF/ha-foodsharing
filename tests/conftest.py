"""Fixtures for testing Foodsharing integration."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def auto_mock_ha():
    """Mock the Home Assistant helpers that require a running instance."""
    import homeassistant.helpers.frame as frame

    patches = [patch("homeassistant.core.HomeAssistant")]
    if hasattr(frame, "report"):
        patches.append(patch("homeassistant.helpers.frame.report"))

    with patch("homeassistant.core.HomeAssistant"):
        if hasattr(frame, "report"):
            with patch("homeassistant.helpers.frame.report"):
                yield
        else:
            yield


@pytest.fixture()
def mock_session():
    """Mock an aiohttp ClientSession."""
    mock = MagicMock()
    return mock
