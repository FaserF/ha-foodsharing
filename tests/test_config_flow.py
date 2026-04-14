from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.foodsharing.config_flow import FoodsharingConfigFlow
from custom_components.foodsharing.const import CONF_EMAIL, CONF_LATITUDE_FS, CONF_PASSWORD


@pytest.mark.asyncio
async def test_config_flow_version() -> None:
    """Test flow version."""
    flow = FoodsharingConfigFlow()
    assert flow.VERSION == 5

@pytest.mark.asyncio
async def test_config_flow_user_step_success(mock_session):
    """Test successful user step (no 2FA)."""
    flow = FoodsharingConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.latitude = 52.52
    flow.hass.config.longitude = 13.405
    flow.context = {}
    flow.hass.config_entries.flow.async_progress_by_handler.return_value = []
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = None

    with patch("custom_components.foodsharing.config_flow.async_get_clientsession", return_value=mock_session):
        # Mock successful login
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"id": 123}
        mock_session.post.return_value.__aenter__.return_value = mock_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        user_input = {
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "password",
            "location": {"latitude": 52.52, "longitude": 13.405, "radius": 7000},
        }

        result = await flow.async_step_user(user_input)
        assert result["type"] == "form"
        assert result["step_id"] == "add_location"

        # Submit add_location form
        result = await flow.async_step_add_location({"add_another": False})

        assert result["type"] == "create_entry"
        assert result["title"] == "test@example.com"
        assert result["data"][CONF_LATITUDE_FS] == 52.52
        assert result["data"][CONF_EMAIL] == "test@example.com"
        # Locations list is built correctly
        assert result["data"]["locations"] == [
            {"latitude": 52.52, "longitude": 13.405, "distance": 7}
        ]

@pytest.mark.asyncio
async def test_config_flow_2fa_required(mock_session):
    """Test scenario where 2FA is required."""
    flow = FoodsharingConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.latitude = 52.52
    flow.hass.config.longitude = 13.405
    flow.context = {}
    flow.hass.config_entries.flow.async_progress_by_handler.return_value = []
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = None

    with patch("custom_components.foodsharing.config_flow.async_get_clientsession", return_value=mock_session):
        # Mock 2FA required response
        mock_response_2fa = AsyncMock()
        mock_response_2fa.status = 400
        mock_response_2fa.json.return_value = {"code": "2fa_required"}

        # Initial check (not logged in)
        mock_response_fail = AsyncMock()
        mock_response_fail.status = 401

        mock_session.get.return_value.__aenter__.return_value = mock_response_fail
        mock_session.post.return_value.__aenter__.return_value = mock_response_2fa

        user_input = {
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "password",
            "location": {"latitude": 52.52, "longitude": 13.405, "radius": 7000},
        }

        result = await flow.async_step_user(user_input)

        # Should proceed to TOTP step
        assert result["type"] == "form"
        assert result["step_id"] == "totp"

        # Test TOTP submission
        mock_response_success = AsyncMock()
        mock_response_success.status = 200
        mock_response_success.json.return_value = {"id": 123}
        mock_session.post.return_value.__aenter__.return_value = mock_response_success

        result_totp = await flow.async_step_totp({"code": "123456"})
        assert result_totp["type"] == "form"
        assert result_totp["step_id"] == "add_location"

        # Submit add_location form
        result = await flow.async_step_add_location({"add_another": False})
        assert result["type"] == "create_entry"
        assert CONF_EMAIL in result["data"]

@pytest.mark.asyncio
async def test_config_flow_user_step_beta_success(mock_session):
    """Test successful user step with Beta API enabled."""
    flow = FoodsharingConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.latitude = 52.52
    flow.hass.config.longitude = 13.405
    flow.context = {}
    flow.hass.config_entries.flow.async_progress_by_handler.return_value = []
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = None

    with patch("custom_components.foodsharing.config_flow.async_get_clientsession", return_value=mock_session):
        # Mock GET calls (CSRF fetch and session check)
        mock_resp_fail = AsyncMock()
        mock_resp_fail.status = 401
        # Need to mock text() for the /login hit and json() for the /api/users/current hit
        mock_resp_fail.text.return_value = "login page"
        mock_resp_fail.json.side_effect = Exception("Not JSON")
        mock_session.get.return_value.__aenter__.return_value = mock_resp_fail
        
        # Mock successful login (POST)
        mock_resp_ok = AsyncMock()
        mock_resp_ok.status = 200
        mock_resp_ok.json.return_value = {"id": 123}
        mock_session.post.return_value.__aenter__.return_value = mock_resp_ok

        user_input = {
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "password",
            "location": {"latitude": 52.52, "longitude": 13.405, "radius": 7000},
            "use_beta_api": True,
        }

        result = await flow.async_step_user(user_input)
        assert result["type"] == "form"
        assert result["step_id"] == "add_location"

        # Submit add_location form
        result = await flow.async_step_add_location({"add_another": False})

        assert result["type"] == "create_entry"
        # Verify that BETA endpoint was used
        from unittest.mock import ANY
        mock_session.post.assert_called_with(
            "https://beta.foodsharing.de/api/login",
            json={"email": "test@example.com", "password": "password", "rememberMe": True},
            timeout=ANY,
            headers=ANY,
        )

@pytest.mark.asyncio
async def test_config_flow_totp_unknown_error(mock_session):
    """Test scenario where TOTP submission results in an unexpected error."""
    flow = FoodsharingConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.latitude = 52.52
    flow.hass.config.longitude = 13.405
    flow.context = {}
    flow.hass.config_entries.flow.async_progress_by_handler.return_value = []
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = None
    flow._user_input = {
        CONF_EMAIL: "test@example.com",
        CONF_PASSWORD: "password",
    }

    with patch("custom_components.foodsharing.config_flow.validate_credentials", side_effect=Exception("Unexpected API failure")):
        result = await flow.async_step_totp({"code": "123456"})

        assert result["type"] == "form"
        assert result["errors"]["base"] == "unknown"
